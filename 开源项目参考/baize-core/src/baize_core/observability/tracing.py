"""OpenTelemetry 分布式追踪。

- trace_id 贯穿全链路
- 工具调用 Span
- 模型调用 Span
- 导出到 Jaeger/Zipkin
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class TracingConfig:
    """追踪配置。"""

    service_name: str = "baize-core"
    exporter_type: str = "otlp"  # otlp, jaeger, zipkin, console
    exporter_endpoint: str = "http://localhost:4317"
    sample_rate: float = 1.0  # 采样率
    enabled: bool = True


class TracingManager:
    """追踪管理器。"""

    def __init__(self, config: TracingConfig) -> None:
        """初始化追踪管理器。

        Args:
            config: 追踪配置
        """
        self._config = config
        self._tracer: Any = None
        self._provider: Any = None
        self._initialized = False

    def initialize(self) -> None:
        """初始化 OpenTelemetry。"""
        if not self._config.enabled:
            logger.info("OpenTelemetry 追踪已禁用")
            return

        if self._initialized:
            return

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import SERVICE_NAME, Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

            # 创建资源
            resource = Resource.create(
                {
                    SERVICE_NAME: self._config.service_name,
                }
            )

            # 创建采样器
            sampler = TraceIdRatioBased(self._config.sample_rate)

            # 创建 TracerProvider
            self._provider = TracerProvider(
                resource=resource,
                sampler=sampler,
            )

            # 添加导出器
            self._add_exporter()

            # 设置全局 TracerProvider
            trace.set_tracer_provider(self._provider)

            # 获取 Tracer
            self._tracer = trace.get_tracer(self._config.service_name)

            self._initialized = True
            logger.info(
                "OpenTelemetry 已初始化: %s -> %s",
                self._config.service_name,
                self._config.exporter_endpoint,
            )

        except ImportError as exc:
            logger.warning("OpenTelemetry 未安装: %s", exc)
        except Exception as exc:
            logger.error("OpenTelemetry 初始化失败: %s", exc)

    def _add_exporter(self) -> None:
        """添加导出器。"""
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        exporter: Any = None
        exporter_type = self._config.exporter_type.lower()

        if exporter_type == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=self._config.exporter_endpoint)

        elif exporter_type == "jaeger":
            # Jaeger 现在推荐使用 OTLP
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=self._config.exporter_endpoint)

        elif exporter_type == "console":
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            exporter = ConsoleSpanExporter()

        if exporter:
            self._provider.add_span_processor(BatchSpanProcessor(exporter))

    def shutdown(self) -> None:
        """关闭追踪。"""
        if self._provider:
            self._provider.shutdown()
            self._initialized = False
            logger.info("OpenTelemetry 已关闭")

    @property
    def tracer(self) -> Any:
        """获取 Tracer。"""
        return self._tracer

    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[Any, None, None]:
        """启动一个 Span。

        Args:
            name: Span 名称
            attributes: Span 属性

        Yields:
            Span 对象
        """
        if not self._tracer:
            yield None
            return

        with self._tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            yield span

    def start_tool_span(
        self,
        tool_name: str,
        task_id: str,
        **kwargs: Any,
    ) -> Any:
        """启动工具调用 Span。"""
        return self.start_span(
            f"tool.{tool_name}",
            attributes={
                "tool.name": tool_name,
                "task.id": task_id,
                **kwargs,
            },
        )

    def start_model_span(
        self,
        model: str,
        stage: str,
        task_id: str,
        **kwargs: Any,
    ) -> Any:
        """启动模型调用 Span。"""
        return self.start_span(
            f"llm.{model}",
            attributes={
                "llm.model": model,
                "llm.stage": stage,
                "task.id": task_id,
                **kwargs,
            },
        )


# 全局 TracingManager 实例
_tracing_manager: TracingManager | None = None


def get_tracing_config_from_env() -> TracingConfig:
    """从环境变量获取追踪配置。"""
    import os

    return TracingConfig(
        service_name=os.getenv("OTEL_SERVICE_NAME", "baize-core"),
        exporter_type=os.getenv("OTEL_EXPORTER_TYPE", "otlp"),
        exporter_endpoint=os.getenv("OTEL_EXPORTER_ENDPOINT", "http://localhost:4317"),
        sample_rate=float(os.getenv("OTEL_SAMPLE_RATE", "1.0")),
        enabled=os.getenv("OTEL_ENABLED", "true").lower() == "true",
    )


def get_tracing_manager() -> TracingManager:
    """获取全局 TracingManager。"""
    global _tracing_manager
    if _tracing_manager is None:
        config = get_tracing_config_from_env()
        _tracing_manager = TracingManager(config)
        _tracing_manager.initialize()
    return _tracing_manager


def get_tracer() -> Any:
    """获取 Tracer。"""
    return get_tracing_manager().tracer


def get_current_trace_id() -> str | None:
    """获取当前 trace_id。"""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span:
            context = span.get_span_context()
            if context and context.is_valid:
                return format(context.trace_id, "032x")
    except Exception:
        pass
    return None


def instrument_function(
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """函数装饰器，自动创建 Span。

    Args:
        name: Span 名称（默认为函数名）
        attributes: 额外属性

    Returns:
        装饰器函数
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            manager = get_tracing_manager()
            with manager.start_span(span_name, attributes):
                return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            manager = get_tracing_manager()
            with manager.start_span(span_name, attributes):
                return func(*args, **kwargs)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def instrument_fastapi(app: Any) -> None:
    """为 FastAPI 应用添加追踪中间件。

    Args:
        app: FastAPI 应用实例
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI 追踪中间件已添加")
    except ImportError:
        logger.warning("opentelemetry-instrumentation-fastapi 未安装")
    except Exception as exc:
        logger.error("FastAPI 追踪中间件添加失败: %s", exc)
