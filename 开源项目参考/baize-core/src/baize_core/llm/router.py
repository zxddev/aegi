"""模型路由器。

按编排阶段选择不同模型，支持 outline/deep_loop/synthesis 三阶段路由。
集成 LiteLLM Router 实现多模型路由、降级与成本控制。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, cast

from baize_core.schemas.policy import StageType

logger = logging.getLogger(__name__)


@dataclass
class StageModelMapping:
    """阶段到模型的映射配置。

    - outline: planner 模型（规划/大纲生成）
    - observe/orient/decide: extractor 模型（抽取/分析）
    - act/synthesis: writer 模型（写作/合成）
    """

    outline: str | None = None
    observe: str | None = None
    orient: str | None = None
    decide: str | None = None
    act: str | None = None
    synthesis: str | None = None

    def get(self, stage: StageType) -> str | None:
        """获取阶段对应的模型。

        Args:
            stage: 编排阶段

        Returns:
            模型名称，未配置时返回 None
        """
        mapping = {
            StageType.OUTLINE: self.outline,
            StageType.OBSERVE: self.observe,
            StageType.ORIENT: self.orient,
            StageType.DECIDE: self.decide,
            StageType.ACT: self.act,
            StageType.SYNTHESIS: self.synthesis,
        }
        return mapping.get(stage)


@dataclass
class ModelSpec:
    """单个模型配置规格。

    Attributes:
        model_name: 路由器内部使用的模型别名
        litellm_model: LiteLLM 模型标识（provider/model 格式）
        api_base: API 基地址（可选，用于本地模型）
        api_key: API 密钥（可选，默认从环境变量读取）
        rpm: 每分钟请求数限制（可选）
        tpm: 每分钟 token 数限制（可选）
    """

    model_name: str
    litellm_model: str
    api_base: str | None = None
    api_key: str | None = None
    rpm: int | None = None
    tpm: int | None = None

    def to_litellm_dict(self) -> dict[str, Any]:
        """转换为 LiteLLM Router 所需的字典格式。"""
        params: dict[str, Any] = {"model": self.litellm_model}
        if self.api_base:
            params["api_base"] = self.api_base
        if self.api_key:
            params["api_key"] = self.api_key
        if self.rpm:
            params["rpm"] = self.rpm
        if self.tpm:
            params["tpm"] = self.tpm
        return {"model_name": self.model_name, "litellm_params": params}


@dataclass
class FallbackSpec:
    """降级配置。

    Attributes:
        primary: 主模型名称
        fallbacks: 降级模型列表（按优先级排序）
    """

    primary: str
    fallbacks: list[str]

    def to_litellm_dict(self) -> dict[str, list[str]]:
        """转换为 LiteLLM Router 所需的字典格式。"""
        return {self.primary: self.fallbacks}


@dataclass
class LiteLLMRouterConfig:
    """LiteLLM Router 配置。

    Attributes:
        models: 模型配置列表
        fallbacks: 降级配置列表
        routing_strategy: 路由策略（simple-shuffle/latency-based-routing/usage-based-routing）
        num_retries: 重试次数
        timeout: 超时时间（秒）
        allowed_fails: 健康检查允许的失败次数
        cooldown_time: 模型冷却时间（秒）
    """

    models: list[ModelSpec] = field(default_factory=list)
    fallbacks: list[FallbackSpec] = field(default_factory=list)
    routing_strategy: str = "simple-shuffle"
    num_retries: int = 2
    timeout: float = 120.0
    allowed_fails: int = 3
    cooldown_time: float = 60.0


@dataclass
class ModelRouterConfig:
    """模型路由配置。

    Attributes:
        stage_mapping: 阶段到模型的映射
        default_model: 默认模型（阶段未配置时使用）
        litellm_config: LiteLLM Router 配置（可选）
    """

    stage_mapping: StageModelMapping = field(default_factory=StageModelMapping)
    default_model: str = "default"
    litellm_config: LiteLLMRouterConfig | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRouterConfig:
        """从字典加载配置。

        Args:
            data: 配置字典

        Returns:
            ModelRouterConfig 实例
        """
        stage_data = data.get("stage_mapping", {})
        stage_mapping = StageModelMapping(
            outline=stage_data.get("outline"),
            observe=stage_data.get("observe"),
            orient=stage_data.get("orient"),
            decide=stage_data.get("decide"),
            act=stage_data.get("act"),
            synthesis=stage_data.get("synthesis"),
        )
        default_model = data.get("default_model", "default")

        # 解析 LiteLLM 配置
        litellm_config: LiteLLMRouterConfig | None = None
        litellm_data = data.get("litellm_config")
        if litellm_data:
            models = [
                ModelSpec(
                    model_name=m["model_name"],
                    litellm_model=m["litellm_model"],
                    api_base=m.get("api_base"),
                    api_key=m.get("api_key"),
                    rpm=m.get("rpm"),
                    tpm=m.get("tpm"),
                )
                for m in litellm_data.get("models", [])
            ]
            fallbacks = [
                FallbackSpec(
                    primary=f["primary"],
                    fallbacks=f["fallbacks"],
                )
                for f in litellm_data.get("fallbacks", [])
            ]
            litellm_config = LiteLLMRouterConfig(
                models=models,
                fallbacks=fallbacks,
                routing_strategy=litellm_data.get("routing_strategy", "simple-shuffle"),
                num_retries=litellm_data.get("num_retries", 2),
                timeout=litellm_data.get("timeout", 120.0),
                allowed_fails=litellm_data.get("allowed_fails", 3),
                cooldown_time=litellm_data.get("cooldown_time", 60.0),
            )

        return cls(
            stage_mapping=stage_mapping,
            default_model=default_model,
            litellm_config=litellm_config,
        )


@dataclass
class RoutingDecision:
    """路由决策记录（用于审计）。

    Attributes:
        requested_model: 请求的模型名称
        selected_model: 实际选择的模型名称
        stage: 编排阶段
        fallback_used: 是否使用了降级
        latency_ms: 选择延迟（毫秒）
        reason: 选择原因
    """

    requested_model: str
    selected_model: str
    stage: str
    fallback_used: bool = False
    latency_ms: int = 0
    reason: str = ""


class ModelRouter:
    """模型路由器。

    根据编排阶段选择适当的模型，支持：
    1. 按阶段选择模型
    2. 阶段未配置时回退到默认模型
    3. LiteLLM Router 集成（多模型路由/降级/成本控制）
    4. 列出所有可用模型
    5. 检查模型是否在允许范围内
    """

    def __init__(self, config: ModelRouterConfig) -> None:
        """初始化路由器。

        Args:
            config: 路由配置
        """
        self._config = config
        self._allowed_models: set[str] = self._build_allowed_models()
        self._litellm_router: Any = None
        self._litellm_available = self._check_litellm_available()

        if config.litellm_config and self._litellm_available:
            self._init_litellm_router(config.litellm_config)

    def _check_litellm_available(self) -> bool:
        """检查 LiteLLM 是否可用。"""
        try:
            import litellm  # noqa: F401

            return True
        except ImportError:
            logger.warning("LiteLLM 未安装，使用简单路由模式")
            return False

    def _init_litellm_router(self, config: LiteLLMRouterConfig) -> None:
        """初始化 LiteLLM Router。"""
        if not config.models:
            logger.warning("LiteLLM 配置为空，跳过初始化")
            return

        try:
            from litellm import Router

            model_list = [spec.to_litellm_dict() for spec in config.models]
            fallbacks_list = [fb.to_litellm_dict() for fb in config.fallbacks]

            self._litellm_router = Router(
                model_list=cast(list[Any], model_list),
                fallbacks=cast(list[Any], fallbacks_list) if fallbacks_list else [],
                routing_strategy=cast(Any, config.routing_strategy),
                num_retries=config.num_retries,
                timeout=config.timeout,
                allowed_fails=config.allowed_fails,
                cooldown_time=config.cooldown_time,
            )
            logger.info("LiteLLM Router 初始化成功，模型数量: %d", len(config.models))
        except Exception as exc:
            logger.error("LiteLLM Router 初始化失败: %s", exc)
            self._litellm_router = None

    def _build_allowed_models(self) -> set[str]:
        """构建允许的模型集合。"""
        models: set[str] = {self._config.default_model}
        mapping = self._config.stage_mapping
        for stage in StageType:
            model = mapping.get(stage)
            if model is not None:
                models.add(model)
        # 添加 LiteLLM 配置中的模型
        if self._config.litellm_config:
            for spec in self._config.litellm_config.models:
                models.add(spec.model_name)
        return models

    @property
    def litellm_router(self) -> Any:
        """获取 LiteLLM Router 实例。"""
        return self._litellm_router

    @property
    def is_litellm_enabled(self) -> bool:
        """检查 LiteLLM Router 是否启用。"""
        return self._litellm_router is not None

    def get_model(self, stage: StageType) -> str:
        """获取阶段对应的模型。

        Args:
            stage: 编排阶段

        Returns:
            模型名称
        """
        model = self._config.stage_mapping.get(stage)
        if model is not None:
            return model
        return self._config.default_model

    def list_models(self) -> list[str]:
        """列出所有配置的模型。

        Returns:
            模型名称列表
        """
        return list(self._allowed_models)

    def get_default_model(self) -> str:
        """获取默认模型。"""
        return self._config.default_model

    def is_model_allowed(self, model: str) -> bool:
        """检查模型是否在允许范围内。

        Args:
            model: 模型名称

        Returns:
            是否允许
        """
        return model in self._allowed_models

    def get_fallbacks(self, model: str) -> list[str]:
        """获取模型的降级列表。

        Args:
            model: 模型名称

        Returns:
            降级模型列表
        """
        if not self._config.litellm_config:
            return (
                [self._config.default_model]
                if model != self._config.default_model
                else []
            )

        for fallback in self._config.litellm_config.fallbacks:
            if fallback.primary == model:
                return fallback.fallbacks

        # 默认降级到 default_model
        if model != self._config.default_model:
            return [self._config.default_model]
        return []

    async def completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        stage: StageType,
        **kwargs: Any,
    ) -> tuple[Any, RoutingDecision]:
        """通过 LiteLLM Router 调用模型。

        Args:
            model: 模型名称
            messages: 消息列表
            stage: 编排阶段
            **kwargs: 其他参数传递给 LiteLLM

        Returns:
            (响应, 路由决策) 元组

        Raises:
            RuntimeError: LiteLLM Router 未启用或调用失败
        """
        import time

        start_time = time.time()

        if not self._litellm_router:
            # 降级到直接调用 litellm
            if not self._litellm_available:
                raise RuntimeError("LiteLLM 未安装")

            import litellm

            response = await asyncio.to_thread(
                litellm.completion,
                model=model,
                messages=messages,
                **kwargs,
            )
            latency_ms = int((time.time() - start_time) * 1000)
            decision = RoutingDecision(
                requested_model=model,
                selected_model=model,
                stage=stage.value,
                fallback_used=False,
                latency_ms=latency_ms,
                reason="直接调用（Router 未启用）",
            )
            return response, decision

        # 使用 LiteLLM Router
        try:
            response = await self._litellm_router.acompletion(
                model=model,
                messages=messages,
                **kwargs,
            )
            latency_ms = int((time.time() - start_time) * 1000)

            # 尝试获取实际使用的模型
            actual_model = model
            if hasattr(response, "_hidden_params"):
                actual_model = response._hidden_params.get("model", model)

            decision = RoutingDecision(
                requested_model=model,
                selected_model=actual_model,
                stage=stage.value,
                fallback_used=actual_model != model,
                latency_ms=latency_ms,
                reason="LiteLLM Router 路由",
            )
            return response, decision

        except Exception as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error("LiteLLM Router 调用失败: %s", exc)
            raise RuntimeError(f"模型调用失败: {exc}") from exc

    async def aembedding(
        self,
        *,
        model: str,
        input_text: str | list[str],
        **kwargs: Any,
    ) -> Any:
        """通过 LiteLLM Router 调用 Embedding 模型。

        Args:
            model: 模型名称
            input_text: 输入文本
            **kwargs: 其他参数

        Returns:
            Embedding 响应
        """
        if not self._litellm_router:
            if not self._litellm_available:
                raise RuntimeError("LiteLLM 未安装")

            import litellm

            return await asyncio.to_thread(
                litellm.embedding,
                model=model,
                input=input_text,
                **kwargs,
            )

        return await self._litellm_router.aembedding(
            model=model,
            input=input_text,
            **kwargs,
        )

    def get_model_info(self, model: str) -> dict[str, Any] | None:
        """获取模型信息。

        Args:
            model: 模型名称

        Returns:
            模型信息字典，未找到返回 None
        """
        if not self._config.litellm_config:
            return None

        for spec in self._config.litellm_config.models:
            if spec.model_name == model:
                return {
                    "model_name": spec.model_name,
                    "litellm_model": spec.litellm_model,
                    "api_base": spec.api_base,
                    "rpm": spec.rpm,
                    "tpm": spec.tpm,
                }
        return None

    def get_healthy_deployments(self) -> list[str]:
        """获取健康的模型部署列表。

        Returns:
            健康模型名称列表
        """
        if not self._litellm_router:
            return list(self._allowed_models)

        try:
            # LiteLLM Router 内部维护健康状态
            healthy = []
            if hasattr(self._litellm_router, "model_list"):
                for deployment in self._litellm_router.model_list:
                    model_name = deployment.get("model_name")
                    if model_name:
                        healthy.append(model_name)
            return healthy if healthy else list(self._allowed_models)
        except Exception:
            return list(self._allowed_models)
