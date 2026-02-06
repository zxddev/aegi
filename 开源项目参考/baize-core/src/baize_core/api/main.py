"""FastAPI 入口。"""

from __future__ import annotations

from fastapi import FastAPI

from baize_core.api.audit_routes import register_audit_chain_routes
from baize_core.api.routes import (
    artifacts_router,
    audit_router,
    entities_router,
    events_router,
    modules_router,
    reports_router,
    reviews_router,
    storm_router,
    system_router,
    tasks_router,
    toolchain_router,
)
from baize_core.config.settings import AppConfig
from baize_core.orchestration.factory import build_orchestrator
from baize_core.replay.service import ReplayService
from baize_core.retention.scheduler import register_retention_cleanup
from baize_core.tools.mcp_client import McpClient


def build_app() -> FastAPI:
    """构建应用实例。"""

    app = FastAPI(title="baize-core", version="0.1.0")
    config = AppConfig.from_env()
    orchestrator = build_orchestrator(config)
    register_retention_cleanup(
        app,
        store=orchestrator.store,
        artifact_store=orchestrator.artifact_store,
        recorder=orchestrator.audit_recorder,
    )
    replay_service = ReplayService(orchestrator.store)
    mcp_audit_client = McpClient(
        base_url=config.mcp.base_url,
        api_key=config.mcp.api_key,
        tls_verify=config.mcp.tls_verify,
    )
    register_audit_chain_routes(
        app,
        store=orchestrator.store,
        mcp_audit_client=mcp_audit_client,
    )

    _setup_tracing(app)
    metrics = _setup_metrics(app)
    app.include_router(system_router(metrics))
    app.include_router(tasks_router(orchestrator))
    app.include_router(reports_router(orchestrator))
    app.include_router(artifacts_router(orchestrator))
    app.include_router(modules_router(orchestrator))
    app.include_router(entities_router(orchestrator))
    app.include_router(events_router(orchestrator))
    app.include_router(toolchain_router(orchestrator))
    app.include_router(storm_router(orchestrator))
    app.include_router(reviews_router(orchestrator))
    app.include_router(audit_router(orchestrator, replay_service))

    return app


_TRACING_INITIALIZED = False


def _setup_tracing(app: FastAPI) -> None:
    """初始化 OpenTelemetry（可选）。"""
    global _TRACING_INITIALIZED

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except ModuleNotFoundError:
        return

    # 避免重复设置 TracerProvider
    if not _TRACING_INITIALIZED:
        current_provider = trace.get_tracer_provider()
        # 只有当前没有有效的 TracerProvider 时才设置
        if not hasattr(current_provider, "add_span_processor"):
            provider = TracerProvider()
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            trace.set_tracer_provider(provider)
        _TRACING_INITIALIZED = True

    FastAPIInstrumentor.instrument_app(app)


_METRICS_INITIALIZED = False
_REQUEST_COUNT = None
_REQUEST_LATENCY = None


def _setup_metrics(app: FastAPI):
    """初始化 Prometheus 指标（可选）。"""
    global _METRICS_INITIALIZED, _REQUEST_COUNT, _REQUEST_LATENCY

    try:
        from prometheus_client import REGISTRY, Counter, Histogram, generate_latest
    except ModuleNotFoundError:
        return None

    # 避免重复注册指标
    if not _METRICS_INITIALIZED:
        # 检查是否已经存在这些指标（可能在之前的进程中注册过）
        existing_names = {c._name for c in REGISTRY._names_to_collectors.values() if hasattr(c, "_name")}
        
        if "baize_core_requests_total" not in existing_names:
            _REQUEST_COUNT = Counter(
                "baize_core_requests_total",
                "Total API requests",
                ["method", "path"],
            )
        else:
            _REQUEST_COUNT = REGISTRY._names_to_collectors.get("baize_core_requests_total")

        if "baize_core_request_latency_seconds" not in existing_names:
            _REQUEST_LATENCY = Histogram(
                "baize_core_request_latency_seconds",
                "API request latency",
                ["method", "path"],
            )
        else:
            _REQUEST_LATENCY = REGISTRY._names_to_collectors.get("baize_core_request_latency_seconds")

        _METRICS_INITIALIZED = True

    request_count = _REQUEST_COUNT
    request_latency = _REQUEST_LATENCY

    @app.middleware("http")
    async def _record_metrics(request, call_next):
        with request_latency.labels(request.method, request.url.path).time():
            response = await call_next(request)
        request_count.labels(request.method, request.url.path).inc()
        return response

    return generate_latest


# 使用 uvicorn --factory 模式启动时，不需要在模块级别创建 app
# uvicorn baize_core.api.main:build_app --factory
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0", port=8600)
