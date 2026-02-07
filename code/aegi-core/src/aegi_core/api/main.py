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
from aegi_core.api.routes.hypotheses import router as hypotheses_router
from aegi_core.api.routes.narratives import router as narratives_router
from aegi_core.api.routes.forecast import router as forecast_router
from aegi_core.api.routes.quality import router as quality_router
from aegi_core.api.routes.orchestration import router as orchestration_router


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # startup
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
        yield
        # shutdown
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
    app.include_router(hypotheses_router)
    app.include_router(narratives_router)
    app.include_router(forecast_router)
    app.include_router(quality_router)
    app.include_router(orchestration_router)

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
