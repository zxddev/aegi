"""模型调用封装。"""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
from dataclasses import dataclass
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel

from baize_core.audit.recorder import AuditRecorder
from baize_core.exceptions import LlmApiError, StructuredGenerationError
from baize_core.llm.prompt_builder import PromptBuilder
from baize_core.llm.router import ModelRouter
from baize_core.llm.structured import (
    GenerationMode,
    ModelCapability,
    OutlinesAdapter,
    StructuredGenerationResult,
    StructuredGenerator,
    build_outlines_prompt,
    detect_model_capability,
    is_outlines_available,
)
from baize_core.policy.budget import BudgetTracker
from baize_core.policy.checker import (
    HumanReviewRequiredError,
    PolicyCheckerMixin,
    PolicyDeniedError,
)
from baize_core.policy.engine import PolicyEngine
from baize_core.schemas.audit import ModelTrace
from baize_core.schemas.content import ContentSource
from baize_core.schemas.policy import (
    ActionType,
    PlannedCost,
    PolicyPayload,
    StageType,
)
from baize_core.storage.postgres import PostgresStore

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# 默认 token 预估值（用于策略检查）
DEFAULT_TOKEN_ESTIMATE = 1000


@dataclass(frozen=True)
class LlmConfig:
    """LLM 调用配置。"""

    provider: str
    model: str
    api_key: str
    api_base: str


class LlmRunner(PolicyCheckerMixin):
    """模型运行器（带策略、预算与审计）。

    支持运行时预算追踪，每次调用后自动扣减 token 和调用次数。
    支持 Outlines 约束解码（本地模型）和 JSON mode（云 API）。
    """

    def __init__(
        self,
        *,
        policy_engine: PolicyEngine,
        recorder: AuditRecorder,
        config: LlmConfig,
        model_router: ModelRouter,
        review_store: PostgresStore,
        budget_tracker: BudgetTracker | None = None,
    ) -> None:
        self._policy_engine = policy_engine
        self._recorder = recorder
        self._config = config
        self._model_router = model_router
        self._review_store = review_store
        self._budget_tracker = budget_tracker
        # Outlines 适配器缓存（按模型名称）
        self._outlines_adapters: dict[str, OutlinesAdapter] = {}

    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        messages: list[dict[str, str]] | None = None,
        stage: StageType,
        task_id: str,
        section_id: str | None = None,
        token_estimate: int = DEFAULT_TOKEN_ESTIMATE,
    ) -> str:
        """生成文本内容。

        Args:
            system: 系统提示
            user: 用户输入
            messages: 预构建 messages（用于 PromptBuilder 隔离）
            stage: 编排阶段
            task_id: 任务 ID
            section_id: 章节 ID（可选）
            token_estimate: 预估 token 消耗（用于策略检查）

        Returns:
            生成的文本

        Raises:
            HumanReviewRequiredError: 需要人工复核
            PolicyDeniedError: 策略拒绝
            BudgetExhaustedError: 预算耗尽
        """
        requested_model = self._model_router.get_model(stage)
        request = self._build_policy_request(
            action=ActionType.MODEL_CALL,
            stage=stage,
            task_id=task_id,
            section_id=section_id,
            payload=PolicyPayload(model=requested_model),
            planned_cost=PlannedCost(token_estimate=token_estimate, tool_timeout_ms=0),
        )
        decision = await self._check_policy(request)

        prepared_messages = messages
        if prepared_messages is None:
            builder = PromptBuilder()
            builder.add_system_instruction(
                system, source_type=ContentSource.INTERNAL, source_ref="llm_runner"
            )
            builder.add_user_query(
                user, source_type=ContentSource.INTERNAL, source_ref="llm_runner"
            )
            prepared_messages = builder.build().messages

        trace_id = f"trace_{uuid4().hex}"
        started_at = time.time()
        model = decision.enforced.selected_model or requested_model
        fallback_model = self._model_router.get_default_model()
        candidates = [model]
        if fallback_model and fallback_model != model:
            candidates.append(fallback_model)
        try:
            text = ""
            current_decision = decision
            for index, candidate in enumerate(candidates):
                if index > 0:
                    fallback_request = self._build_policy_request(
                        action=ActionType.MODEL_CALL,
                        stage=stage,
                        task_id=task_id,
                        section_id=section_id,
                        payload=PolicyPayload(model=candidate),
                        planned_cost=PlannedCost(
                            token_estimate=token_estimate, tool_timeout_ms=0
                        ),
                    )
                    current_decision = await self._check_policy(fallback_request)
                try:
                    text = await self._call_litellm_messages(
                        messages=prepared_messages, model=candidate, stage=stage
                    )
                    model = candidate
                    break
                except Exception as exc:
                    # 记录 fallback 失败，尝试下一个候选模型
                    duration_ms = int((time.time() - started_at) * 1000)
                    logger.warning(
                        "模型 %s 调用失败，尝试 fallback: %s", candidate, exc
                    )
                    await self._recorder.record_model_trace(
                        ModelTrace(
                            trace_id=f"{trace_id}_fallback",
                            model=candidate,
                            stage=stage.value,
                            task_id=task_id,
                            duration_ms=duration_ms,
                            success=False,
                            error_type=type(exc).__name__,
                            error_message=str(exc),
                            policy_decision_id=current_decision.decision_id,
                        )
                    )
                    if candidate == candidates[-1]:
                        # 所有候选模型都失败，封装为 LlmApiError 抛出
                        raise LlmApiError(f"所有模型调用失败: {exc}") from exc
            duration_ms = int((time.time() - started_at) * 1000)

            # 调用成功后扣减预算
            if self._budget_tracker is not None:
                # 扣减模型调用次数
                self._budget_tracker.deduct_model_call()
                # 扣减 token 预算（使用预估值，实际值需要从响应中获取）
                self._budget_tracker.deduct_tokens(token_estimate)

            await self._recorder.record_model_trace(
                ModelTrace(
                    trace_id=trace_id,
                    model=model,
                    stage=stage.value,
                    task_id=task_id,
                    duration_ms=duration_ms,
                    success=True,
                    result_ref=text[:256],
                    policy_decision_id=current_decision.decision_id,
                )
            )
            return text
        except LlmApiError:
            # 已经是 LlmApiError，直接传播（来自 fallback 失败）
            raise
        except Exception as exc:
            # 未预期的错误，记录日志并封装为 LlmApiError
            duration_ms = int((time.time() - started_at) * 1000)
            logger.exception("LLM 调用发生未预期错误: %s", exc)
            await self._recorder.record_model_trace(
                ModelTrace(
                    trace_id=trace_id,
                    model=model,
                    stage=stage.value,
                    task_id=task_id,
                    duration_ms=duration_ms,
                    success=False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    policy_decision_id=decision.decision_id,
                )
            )
            raise LlmApiError(f"LLM 调用失败: {exc}") from exc

    async def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        stage: StageType,
        task_id: str,
        section_id: str | None = None,
        token_estimate: int = DEFAULT_TOKEN_ESTIMATE,
        max_retries: int = 3,
        mode: GenerationMode | None = None,
    ) -> StructuredGenerationResult:
        """生成结构化输出。

        三段式保障流程：
        1. Schema 定义（Pydantic）
        2. 生成时约束（云 API 用 JSON mode，本地模型用 Outlines）
        3. 落地前校验（Pydantic 校验失败 → 重试 → 降级/人工介入）

        自动检测模型类型并选择最佳生成模式：
        - 本地模型（ollama/vllm/llamacpp）：使用 Outlines 约束解码
        - 云 API（OpenAI/DeepSeek/Claude 等）：使用 JSON mode
        - 其他：使用后置校验

        Args:
            system: 系统提示
            user: 用户输入
            schema: 目标 Pydantic schema
            stage: 编排阶段
            task_id: 任务 ID
            section_id: 章节 ID（可选）
            token_estimate: 预估 token 消耗
            max_retries: 最大重试次数
            mode: 生成模式（None 表示自动检测）

        Returns:
            结构化生成结果

        Raises:
            StructuredGenerationError: 校验失败且重试耗尽
            RuntimeError: 策略拒绝或需要人工复核
            BudgetExhaustedError: 预算耗尽
        """
        # 获取当前阶段的模型
        model = self._model_router.get_model(stage)

        # 自动检测生成模式
        if mode is None:
            mode = self._detect_generation_mode(model)

        # 如果是 Outlines 模式且可用，使用 Outlines 约束解码
        if mode == GenerationMode.OUTLINES and is_outlines_available():
            return await self._generate_with_outlines(
                system=system,
                user=user,
                schema=schema,
                stage=stage,
                task_id=task_id,
                section_id=section_id,
                token_estimate=token_estimate,
                model=model,
            )

        # 使用标准生成 + 后置校验
        generator = StructuredGenerator(default_mode=mode, max_retries=max_retries)

        # 构建带 schema 约束的提示词
        structured_user = generator.build_structured_prompt(user, schema)

        all_errors: list[str] = []
        last_raw_text = ""

        for attempt in range(max_retries):
            # 生成文本
            raw_text = await self.generate_text(
                system=system,
                user=structured_user,
                stage=stage,
                task_id=task_id,
                section_id=section_id,
                token_estimate=token_estimate,
            )
            last_raw_text = raw_text

            # 尝试解析和校验
            try:
                result = generator.parse_with_validation(raw_text, schema)
                # 记录重试次数
                return StructuredGenerationResult(
                    data=result.data,
                    raw_text=raw_text,
                    mode_used=mode,
                    retries=attempt,
                    validation_errors=all_errors,
                )
            except StructuredGenerationError as exc:
                all_errors.extend(exc.validation_errors)
                # 如果是最后一次重试，抛出错误
                if attempt == max_retries - 1:
                    raise StructuredGenerationError(
                        message=f"结构化输出校验失败，已重试 {max_retries} 次",
                        raw_text=last_raw_text,
                        validation_errors=all_errors,
                        retries=max_retries,
                    ) from exc
                # 否则继续重试，在提示词中加入错误反馈
                error_feedback = "\n".join(f"- {err}" for err in exc.validation_errors)
                structured_user = (
                    f"{generator.build_structured_prompt(user, schema)}\n\n"
                    f"上次输出存在以下问题，请修正：\n{error_feedback}"
                )

        # 理论上不会到达这里
        raise StructuredGenerationError(
            message="结构化输出失败",
            raw_text=last_raw_text,
            validation_errors=all_errors,
            retries=max_retries,
        )

    def _detect_generation_mode(self, model: str) -> GenerationMode:
        """检测模型的最佳生成模式。

        Args:
            model: 模型名称

        Returns:
            推荐的生成模式
        """
        capability = detect_model_capability(model)
        if capability == ModelCapability.OUTLINES:
            return GenerationMode.OUTLINES
        elif capability == ModelCapability.JSON_MODE:
            return GenerationMode.JSON_MODE
        else:
            return GenerationMode.POST_VALIDATE

    def _get_outlines_adapter(self, model: str) -> OutlinesAdapter:
        """获取或创建 Outlines 适配器。

        Args:
            model: 模型名称

        Returns:
            OutlinesAdapter 实例
        """
        if model not in self._outlines_adapters:
            # 解析模型后端
            backend = "transformers"
            model_path = model
            if model.startswith("ollama/"):
                # Ollama 模型需要特殊处理
                backend = "transformers"
                model_path = model.replace("ollama/", "")
            elif model.startswith("vllm/"):
                backend = "vllm"
                model_path = model.replace("vllm/", "")
            elif model.startswith("llamacpp/"):
                backend = "llamacpp"
                model_path = model.replace("llamacpp/", "")

            self._outlines_adapters[model] = OutlinesAdapter(
                model_name=model_path,
                model_backend=backend,
            )
        return self._outlines_adapters[model]

    async def _generate_with_outlines(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        stage: StageType,
        task_id: str,
        section_id: str | None = None,
        token_estimate: int = DEFAULT_TOKEN_ESTIMATE,
        model: str,
    ) -> StructuredGenerationResult:
        """使用 Outlines 约束解码生成结构化输出。

        Args:
            system: 系统提示
            user: 用户输入
            schema: 目标 Pydantic schema
            stage: 编排阶段
            task_id: 任务 ID
            section_id: 章节 ID
            token_estimate: 预估 token 消耗
            model: 模型名称

        Returns:
            结构化生成结果

        Raises:
            StructuredGenerationError: 生成或校验失败
            HumanReviewRequiredError: 需要人工复核
            PolicyDeniedError: 策略拒绝
        """
        # 使用 Mixin 提供的 _check_policy 方法进行策略检查
        # 自动处理预算获取、审计记录、人工复核请求
        request = self._build_policy_request(
            action=ActionType.MODEL_CALL,
            stage=stage,
            task_id=task_id,
            section_id=section_id,
            payload=PolicyPayload(model=model),
            planned_cost=PlannedCost(token_estimate=token_estimate, tool_timeout_ms=0),
        )
        decision = await self._check_policy(request)

        # 构建 Outlines 提示词
        prompt = build_outlines_prompt(system, user, schema)

        # 获取适配器并生成
        adapter = self._get_outlines_adapter(model)

        trace_id = f"trace_{uuid4().hex}"
        started_at = time.time()

        try:
            # Outlines 生成是同步的，需要在线程中执行
            result = await asyncio.to_thread(
                adapter.generate,
                prompt,
                schema,
                token_estimate,  # 作为 max_tokens
            )

            duration_ms = int((time.time() - started_at) * 1000)

            # 扣减预算
            if self._budget_tracker is not None:
                self._budget_tracker.deduct_model_call()
                self._budget_tracker.deduct_tokens(token_estimate)

            # 记录审计
            await self._recorder.record_model_trace(
                ModelTrace(
                    trace_id=trace_id,
                    model=model,
                    stage=stage.value,
                    task_id=task_id,
                    duration_ms=duration_ms,
                    success=True,
                    result_ref=result.raw_text[:256],
                    policy_decision_id=decision.decision_id,
                )
            )

            return result

        except StructuredGenerationError:
            duration_ms = int((time.time() - started_at) * 1000)
            await self._recorder.record_model_trace(
                ModelTrace(
                    trace_id=trace_id,
                    model=model,
                    stage=stage.value,
                    task_id=task_id,
                    duration_ms=duration_ms,
                    success=False,
                    error_type="StructuredGenerationError",
                    error_message="Outlines 结构化输出失败",
                    policy_decision_id=decision.decision_id,
                )
            )
            raise
        except Exception as exc:
            # 未预期的 Outlines 错误，记录日志并封装
            duration_ms = int((time.time() - started_at) * 1000)
            logger.exception("Outlines 生成发生未预期错误: %s", exc)
            await self._recorder.record_model_trace(
                ModelTrace(
                    trace_id=trace_id,
                    model=model,
                    stage=stage.value,
                    task_id=task_id,
                    duration_ms=duration_ms,
                    success=False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    policy_decision_id=decision.decision_id,
                )
            )
            raise StructuredGenerationError(
                message=f"Outlines 生成失败: {exc}",
                raw_text="",
                validation_errors=[str(exc)],
            ) from exc

    async def _call_litellm_messages(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        stage: StageType,
    ) -> str:
        """调用 LiteLLM。

        优先使用 ModelRouter 的 LiteLLM Router（如果启用），
        否则降级到直接调用 litellm。
        """
        # 优先使用 ModelRouter 的 LiteLLM Router
        if self._model_router.is_litellm_enabled:
            try:
                response, _ = await self._model_router.completion(
                    model=model,
                    messages=messages,
                    stage=stage,
                )
                return self._extract_response_text(response)
            except Exception as exc:
                # 如果 Router 调用失败，尝试降级到直接调用
                logger.warning(
                    "LiteLLM Router 调用失败，尝试降级到直接调用: %s", exc
                )

        # 直接调用 Responses API（带重试机制）
        api_base = self._config.api_base.strip()
        # 确保 URL 以 /responses 结尾
        if not api_base.endswith("/responses"):
            api_base = api_base.rstrip("/") + "/responses"
        
        # 转换消息格式为 Responses API 格式
        input_payload = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            input_payload.append({
                "type": "message",
                "role": role,
                "content": [
                    {
                        "type": "input_text",
                        "text": content
                    }
                ]
            })
        
        request_body = {
            "model": model,
            "input": input_payload,
            "stream": False,
            "include": ["reasoning.encrypted_content"],
        }

        async def _async_call() -> dict:
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    api_base,
                    json=request_body,
                    headers={
                        "Authorization": f"Bearer {self._config.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                # 如果是错误状态码，先保存响应体再抛出异常
                if response.status_code >= 400:
                    response_body = response.text
                    error_msg = f"HTTP {response.status_code}: {response_body[:2000]}"
                    raise httpx.HTTPStatusError(
                        error_msg,
                        request=response.request,
                        response=response,
                    )
                return response.json()

        # 重试机制：处理间歇性服务器错误和网络问题
        max_retries = 5
        retry_delay = 2.0  # 初始延迟秒数
        last_error: Exception | None = None
        error_log_path = "/home/user/workspace/gitcode/baizeai/logs/llm_errors.jsonl"
        
        # 可重试的错误模式
        retryable_patterns = [
            "500", "502", "503", "504",  # 服务器错误
            "internal", "timeout", "timed out",  # 超时
            "readerror", "read error", "connection",  # 网络错误
            "reset", "closed", "refused",  # 连接问题
        ]
        
        def _log_error(attempt: int, error: Exception, is_final: bool = False) -> None:
            """记录 LLM 调用错误到文件"""
            import json
            import os
            from datetime import datetime
            
            os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
            
            error_record = {
                "timestamp": datetime.now().isoformat(),
                "model": model,
                "api_base": api_base,
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "is_final_failure": is_final,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "request_body": {
                    "model": request_body.get("model"),
                    "input_length": len(request_body.get("input", [])),
                    "stream": request_body.get("stream"),
                },
            }
            
            try:
                with open(error_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(error_record, ensure_ascii=False) + "\n")
            except Exception as log_err:
                logger.error("无法写入 LLM 错误日志: %s", log_err)
        
        for attempt in range(max_retries):
            try:
                response = await _async_call()
                return self._extract_response_text_legacy(response)
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                error_type = type(e).__name__.lower()
                
                # 记录错误到文件
                is_final = attempt >= max_retries - 1
                _log_error(attempt, e, is_final=is_final)
                
                # 检查是否是可重试的错误
                is_retryable = any(
                    pattern in error_str or pattern in error_type 
                    for pattern in retryable_patterns
                )
                
                if is_retryable and attempt < max_retries - 1:
                    logger.warning(
                        "LLM 调用失败（尝试 %d/%d），%0.1f秒后重试: %s: %s",
                        attempt + 1, max_retries, retry_delay, type(e).__name__, e
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30.0)  # 指数退避，最大30秒
                    continue
                # 对于不可重试的错误，直接抛出
                raise
        
        # 所有重试都失败
        if last_error:
            raise last_error
        raise RuntimeError("LLM 调用失败（重试耗尽）")

    def _extract_response_text(self, response: object) -> str:
        """从 LiteLLM completion 响应中提取文本。

        Args:
            response: LiteLLM completion 响应

        Returns:
            提取的文本内容

        Raises:
            ValueError: 无法提取文本
        """
        # 标准 OpenAI 格式响应
        choices = _get_field(response, "choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            message = _get_field(first_choice, "message")
            if message:
                content = _get_field(message, "content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

        # 尝试其他格式
        content = _get_field(response, "content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        raise ValueError("无法从模型响应中提取文本内容")

    def _extract_response_text_legacy(self, response: object) -> str:
        """从旧版 LiteLLM responses API 响应中提取文本。

        Args:
            response: LiteLLM responses 响应

        Returns:
            提取的文本内容

        Raises:
            ValueError: 无法提取文本
        """
        output = _get_field(response, "output")
        if not isinstance(output, list) or not output:
            raise ValueError("模型返回缺少 output")
        for item in output:
            content = _get_field(item, "content")
            if not isinstance(content, list):
                continue
            texts: list[str] = []
            for block in content:
                if _get_field(block, "type") != "output_text":
                    continue
                text = _get_field(block, "text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
            if texts:
                return "\n".join(texts)
        raise ValueError("模型返回缺少文本内容")


def _get_field(value: object, key: str) -> object:
    """读取响应字段。"""

    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
