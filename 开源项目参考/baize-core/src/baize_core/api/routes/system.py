"""系统接口。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Response


def get_router(metrics: Callable[[], bytes] | None) -> APIRouter:
    """系统路由。"""
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, str]:
        """健康检查。"""
        return {"status": "ok"}

    @router.get("/metrics")
    async def metrics_endpoint() -> Response:
        """Prometheus 指标。"""
        if metrics is None:
            raise HTTPException(status_code=503, detail="metrics 未启用")
        return Response(metrics(), media_type="text/plain; version=0.0.4")

    return router
