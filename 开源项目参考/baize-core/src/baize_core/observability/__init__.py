"""可观测性模块。

提供 OpenTelemetry 分布式追踪和 Prometheus 指标能力：
- trace_id 贯穿全链路
- 工具调用 Span
- 模型调用 Span
- 性能指标收集
"""

from baize_core.observability.metrics import (
    MetricsConfig,
    MetricsManager,
    get_metrics_manager,
)
from baize_core.observability.tracing import (
    TracingConfig,
    TracingManager,
    get_current_trace_id,
    get_tracer,
    instrument_function,
)

__all__ = [
    "TracingConfig",
    "TracingManager",
    "get_tracer",
    "get_current_trace_id",
    "instrument_function",
    "MetricsConfig",
    "MetricsManager",
    "get_metrics_manager",
]
