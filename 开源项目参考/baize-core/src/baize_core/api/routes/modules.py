"""报告模块接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from baize_core.modules.registry import ModuleRegistry
from baize_core.schemas.storm import ReportModuleSpec


def get_router(orchestrator: Any) -> APIRouter:
    """模块相关路由。"""

    router = APIRouter()
    registry = ModuleRegistry(orchestrator.store.session_factory)

    @router.get("/modules", response_model=list[ReportModuleSpec])
    async def list_modules(
        parent_id: str | None = Query(default=None),
        include_inactive: bool = Query(default=False),
    ) -> list[ReportModuleSpec]:
        """获取模块列表（支持层级）。"""

        return await registry.list_modules(
            parent_id=parent_id, include_inactive=include_inactive
        )

    @router.get("/modules/{module_id}", response_model=ReportModuleSpec)
    async def get_module(module_id: str) -> ReportModuleSpec:
        """获取模块详情。"""

        module = await registry.get_module(module_id, include_inactive=True)
        if module is None:
            raise HTTPException(status_code=404, detail="模块不存在")
        return module

    @router.post("/modules", response_model=dict[str, str])
    async def upsert_module(payload: ReportModuleSpec) -> dict[str, str]:
        """创建或更新模块。"""

        await registry.upsert_module(payload)
        return {"status": "ok", "module_id": payload.module_id}

    return router

