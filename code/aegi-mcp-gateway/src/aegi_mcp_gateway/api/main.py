# Author: msq

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from aegi_mcp_gateway.api.errors import GatewayHTTPError
from aegi_mcp_gateway.api.routes.tools import router as tools_router


def create_app() -> FastAPI:
    app = FastAPI(title="aegi-mcp-gateway", version="0.0.0")

    app.include_router(tools_router)

    @app.exception_handler(GatewayHTTPError)
    async def gateway_http_error_handler(
        request: Request,
        exc: GatewayHTTPError,
    ) -> JSONResponse:
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
        return {"ok": True, "service": "aegi-mcp-gateway"}

    return app


app = create_app()
