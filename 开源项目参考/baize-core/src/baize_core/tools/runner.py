"""工具调用包装。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from baize_core.audit.recorder import AuditRecorder
from baize_core.exceptions import ToolInvocationError
from baize_core.llm.sanitizer import ToolOutputSanitizer
from baize_core.policy.budget import BudgetTracker
from baize_core.policy.checker import PolicyCheckerMixin
from baize_core.policy.engine import PolicyEngine
from baize_core.schemas.audit import ToolTrace
from baize_core.schemas.policy import (
    ActionType,
    PlannedCost,
    PolicyDecision,
    PolicyPayload,
    StageType,
)
from baize_core.storage.postgres import PostgresStore
from baize_core.tools.mcp_client import McpClient

# 默认工具超时（毫秒）
DEFAULT_TOOL_TIMEOUT_MS = 30000

logger = logging.getLogger(__name__)


class ToolRunner(PolicyCheckerMixin):
    """工具运行器（带策略、预算与审计）。

    支持运行时预算追踪，每次调用后自动扣减工具调用次数。
    """

    def __init__(
        self,
        policy_engine: PolicyEngine,
        recorder: AuditRecorder,
        mcp_client: McpClient,
        review_store: PostgresStore,
        budget_tracker: BudgetTracker | None = None,
    ) -> None:
        self._policy_engine = policy_engine
        self._recorder = recorder
        self._mcp_client = mcp_client
        self._review_store = review_store
        self._budget_tracker = budget_tracker
        self._concurrency_semaphore: asyncio.Semaphore | None = None
        self._concurrency_limit: int | None = None
        self._tool_output_sanitizer: ToolOutputSanitizer | None = None

    async def run(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, object],
        stage: StageType,
        task_id: str,
        handler: Callable[[dict[str, object], str, str | None], Awaitable[object]],
        timeout_ms: int = DEFAULT_TOOL_TIMEOUT_MS,
    ) -> object:
        """执行工具调用。

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            stage: 编排阶段
            task_id: 任务 ID
            handler: 工具处理函数
            timeout_ms: 超时时间（毫秒）

        Returns:
            工具调用结果

        Raises:
            HumanReviewRequiredError: 需要人工复核
            PolicyDeniedError: 策略拒绝
            BudgetExhaustedError: 预算耗尽
        """
        request = self._build_policy_request(
            action=ActionType.TOOL_CALL,
            stage=stage,
            task_id=task_id,
            payload=PolicyPayload(tool_name=tool_name, tool_input=tool_input),
            planned_cost=PlannedCost(token_estimate=0, tool_timeout_ms=timeout_ms),
        )
        decision = await self._check_policy(request)

        enforced_input = _apply_enforced_limits(tool_input, decision)

        semaphore = self._resolve_concurrency(decision)
        if semaphore is not None:
            await semaphore.acquire()

        trace_id = f"trace_{uuid4().hex}"
        started_at = time.time()
        try:
            result = await handler(enforced_input, trace_id, decision.decision_id)
            duration_ms = int((time.time() - started_at) * 1000)

            # 调用成功后扣减工具调用次数
            if self._budget_tracker is not None:
                self._budget_tracker.deduct_tool_call()

            await self._recorder.record_tool_trace(
                ToolTrace(
                    trace_id=trace_id,
                    tool_name=tool_name,
                    task_id=task_id,
                    duration_ms=duration_ms,
                    success=True,
                    result_ref=str(result)[:256],
                    policy_decision_id=decision.decision_id,
                )
            )
            return result
        except ToolInvocationError:
            # 已经是 ToolInvocationError，直接传播
            raise
        except Exception as exc:
            # 未预期的工具错误，记录日志并封装
            duration_ms = int((time.time() - started_at) * 1000)
            logger.exception("工具 %s 调用发生未预期错误: %s", tool_name, exc)
            await self._recorder.record_tool_trace(
                ToolTrace(
                    trace_id=trace_id,
                    tool_name=tool_name,
                    task_id=task_id,
                    duration_ms=duration_ms,
                    success=False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    policy_decision_id=decision.decision_id,
                )
            )
            raise ToolInvocationError(f"工具 {tool_name} 调用失败: {exc}") from exc
        finally:
            if semaphore is not None:
                semaphore.release()

    async def run_mcp(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, object],
        stage: StageType,
        task_id: str,
    ) -> dict[str, object]:
        """通过 MCP Gateway 调用工具。"""

        async def _handler(
            payload: dict[str, object], trace_id: str, policy_decision_id: str | None
        ) -> dict[str, object]:
            raw = await self._mcp_client.invoke(
                tool_name=tool_name,
                payload=payload,
                trace_id=trace_id,
                policy_decision_id=policy_decision_id,
            )
            if not isinstance(raw, dict):
                raise ValueError("工具调用返回类型不正确")
            sanitizer = self._tool_output_sanitizer
            if sanitizer is None:
                sanitizer = ToolOutputSanitizer()
                self._tool_output_sanitizer = sanitizer
            sanitized, report = sanitizer.sanitize(tool_name=tool_name, payload=raw)
            if report.has_dangerous:
                logger.warning(
                    "工具输出疑似提示注入: trace_id=%s task_id=%s tool=%s fields=%s",
                    trace_id,
                    task_id,
                    tool_name,
                    report.dangerous_fields,
                )
            return sanitized

        result = await self.run(
            tool_name=tool_name,
            tool_input=tool_input,
            stage=stage,
            task_id=task_id,
            handler=_handler,
        )
        if not isinstance(result, dict):
            raise ValueError("工具调用返回类型不正确")
        return result

    def _resolve_concurrency(
        self, decision: PolicyDecision
    ) -> asyncio.Semaphore | None:
        """解析并发限制。"""

        limit = decision.enforced.max_concurrency
        if limit is None:
            return None
        if limit <= 0:
            raise ValueError("并发上限必须大于 0")
        if self._concurrency_semaphore is None or self._concurrency_limit != limit:
            self._concurrency_semaphore = asyncio.Semaphore(limit)
            self._concurrency_limit = limit
        return self._concurrency_semaphore


def _apply_enforced_limits(
    tool_input: dict[str, object], decision: PolicyDecision
) -> dict[str, object]:
    """应用策略强制限制。"""

    enforced = decision.enforced
    payload = dict(tool_input)
    if enforced.timeout_ms is not None and "timeout_ms" in payload:
        payload["timeout_ms"] = enforced.timeout_ms
    if enforced.max_pages is not None and "max_pages" in payload:
        payload["max_pages"] = enforced.max_pages
    if enforced.max_iterations is not None and "max_iterations" in payload:
        payload["max_iterations"] = enforced.max_iterations
    if enforced.min_sources is not None and "min_sources" in payload:
        payload["min_sources"] = enforced.min_sources
    return payload
