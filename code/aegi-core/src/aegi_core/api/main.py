from fastapi import FastAPI

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from aegi_core.api.errors import AegiHTTPError
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


def create_app() -> FastAPI:
    app = FastAPI(title="aegi-core", version="0.0.0")

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

    @app.exception_handler(AegiHTTPError)
    async def aegi_http_error_handler(request: Request, exc: AegiHTTPError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "validation_error",
                "message": "Validation error",
                "details": {"errors": exc.errors()},
            },
        )

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

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": "http_error",
                "message": "HTTP error",
                "details": {"status_code": exc.status_code, "detail": exc.detail},
            },
        )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "aegi-core"}

    return app


app = create_app()
