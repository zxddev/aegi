# Author: msq
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from aegi_core.api.errors import AegiHTTPError
from aegi_core.contracts.errors import ProblemDetail
from aegi_core.api.routes.artifacts import router as artifacts_router
from aegi_core.api.routes.assertions import router as assertions_router
from aegi_core.api.routes.cases import router as cases_router
from aegi_core.api.routes.evidence import router as evidence_router
from aegi_core.api.routes.judgments import router as judgments_router
from aegi_core.api.routes.source_claims import router as source_claims_router
from aegi_core.api.routes.pipelines import router as pipelines_router
from aegi_core.api.routes.tool_traces import router as tool_traces_router
from aegi_core.api.routes.chat import router as chat_router
from aegi_core.api.routes.kg import router as kg_router
from aegi_core.api.routes.links import router as links_router
from aegi_core.api.routes.hypotheses import router as hypotheses_router
from aegi_core.api.routes.narratives import router as narratives_router
from aegi_core.api.routes.forecast import router as forecast_router
from aegi_core.api.routes.quality import router as quality_router
from aegi_core.api.routes.orchestration import router as orchestration_router
from aegi_core.api.routes.ingest import router as ingest_router
from aegi_core.api.routes.search import router as search_router
from aegi_core.api.routes.admin import router as admin_router
from aegi_core.api.routes.reports import router as reports_router
from aegi_core.api.routes.kg_viz import router as kg_viz_router
from aegi_core.api.routes.collection import router as collection_router
from aegi_core.api.routes.pipeline_stream import router as pipeline_stream_router
from aegi_core.api.routes.persona import router as persona_router
from aegi_core.api.routes.subscriptions import router as subscriptions_router
from aegi_core.api.routes.gdelt import router as gdelt_router
from aegi_core.api.routes.bayesian import (
    router as bayesian_router,
    override_router as bayesian_override_router,
)
from aegi_core.openclaw.tools import router as openclaw_tools_router
from aegi_core.ws.handler import router as ws_router, set_gateway_client


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动
        from aegi_core.api.deps import (
            get_neo4j_store,
            get_qdrant_store,
            get_minio_store,
        )

        neo = get_neo4j_store()
        await neo.connect()
        await neo.ensure_indexes()
        qdrant = get_qdrant_store()
        await qdrant.connect()
        minio = get_minio_store()
        await minio.connect()

        # OpenClaw Gateway（可选 — 没配置就跳过）
        from aegi_core.settings import settings

        gateway = None
        if settings.openclaw_gateway_url:
            from aegi_core.openclaw.gateway_client import GatewayClient

            gateway = GatewayClient(
                url=settings.openclaw_gateway_url,
                token=settings.openclaw_gateway_token,
            )
            try:
                await gateway.connect()
                set_gateway_client(gateway)
                from aegi_core.openclaw.dispatch import set_gateway

                set_gateway(gateway)
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "OpenClaw Gateway not available, chat disabled"
                )
                gateway = None

        # 加载 playbook + stage 注册表
        from pathlib import Path
        from aegi_core.services.stages.playbook import load_playbooks
        from aegi_core.services.stages.base import stage_registry  # noqa: F401 — triggers discovery

        _pb_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "deploy"
            / "playbooks.yaml"
        )
        if _pb_path.exists():
            load_playbooks(_pb_path)

        # ── 初始化 EventBus + 注册 PushEngine 处理器 ──
        from aegi_core.services.event_bus import get_event_bus
        from aegi_core.services.push_engine import create_push_handler

        bus = get_event_bus()
        # Review mod A: 独立的 QdrantStore 给 expert_profiles 用
        expert_qdrant = None
        try:
            from aegi_core.infra.qdrant_store import QdrantStore

            expert_qdrant = QdrantStore(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                collection=settings.event_push_expert_collection,
            )
            await expert_qdrant.connect()
        except Exception:
            import logging as _log

            _log.getLogger(__name__).warning(
                "Expert profiles Qdrant not available, semantic match disabled"
            )
            expert_qdrant = None
        push_handler = create_push_handler(qdrant=expert_qdrant, llm=None)
        bus.on("*", push_handler)

        # ── 注册贝叶斯 ACH 处理器，监听 claim.extracted ──
        from aegi_core.services.bayesian_ach import create_bayesian_update_handler
        from aegi_core.api.deps import get_llm_client as _get_llm

        try:
            _llm = _get_llm()
        except Exception:
            _llm = None
        if _llm:
            bayesian_handler = create_bayesian_update_handler(llm=_llm)
            bus.on("claim.extracted", bayesian_handler)

        yield
        # 关闭
        # ── 优雅关闭：排空事件总线 ──
        bus = get_event_bus()
        await bus.drain()

        if expert_qdrant:
            await expert_qdrant.close()
        if gateway:
            await gateway.close()
        await neo.close()
        await qdrant.close()
        await minio.close()

    app = FastAPI(title="aegi-core", version="0.0.0", lifespan=lifespan)

    app.include_router(cases_router)
    app.include_router(artifacts_router)
    app.include_router(evidence_router)
    app.include_router(source_claims_router)
    app.include_router(assertions_router)
    app.include_router(judgments_router)
    app.include_router(tool_traces_router)
    app.include_router(pipelines_router)
    app.include_router(chat_router)
    app.include_router(kg_router)
    app.include_router(links_router)
    app.include_router(hypotheses_router)
    app.include_router(narratives_router)
    app.include_router(forecast_router)
    app.include_router(quality_router)
    app.include_router(orchestration_router)
    app.include_router(ingest_router)
    app.include_router(search_router)
    app.include_router(admin_router)
    app.include_router(reports_router)
    app.include_router(kg_viz_router)
    app.include_router(collection_router)
    app.include_router(pipeline_stream_router)
    app.include_router(persona_router)
    app.include_router(subscriptions_router)
    app.include_router(gdelt_router)
    app.include_router(bayesian_router)
    app.include_router(bayesian_override_router)
    app.include_router(openclaw_tools_router)
    app.include_router(ws_router)

    @app.exception_handler(AegiHTTPError)
    async def aegi_http_error_handler(
        request: Request, exc: AegiHTTPError
    ) -> JSONResponse:
        pd = exc.to_problem_detail()
        content = pd.model_dump()
        # 向后兼容：保留旧 message/details 字段
        content["message"] = exc.message
        content["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        pd = ProblemDetail(
            type="urn:aegi:error:validation",
            title="Validation error",
            status=422,
            detail="Validation error",
            error_code="validation_error",
            extensions={"errors": exc.errors()},
        )
        return JSONResponse(status_code=422, content=pd.model_dump())

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        if isinstance(exc.detail, dict) and {
            "error_code",
            "message",
            "details",
        }.issubset(exc.detail.keys()):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)

        pd = ProblemDetail(
            type="urn:aegi:error:http",
            title="HTTP error",
            status=exc.status_code,
            detail=str(exc.detail),
            error_code="http_error",
            extensions={"status_code": exc.status_code},
        )
        return JSONResponse(status_code=exc.status_code, content=pd.model_dump())

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "aegi-core"}

    return app


app = create_app()
