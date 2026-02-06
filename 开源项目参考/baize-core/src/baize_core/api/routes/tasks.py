"""任务接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from baize_core.schemas.task import TaskResponse, TaskSpec


def get_router(orchestrator: Any) -> APIRouter:
    """任务相关路由。"""
    router = APIRouter()

    @router.post("/tasks", response_model=TaskResponse)
    async def submit_task(task: TaskSpec) -> TaskResponse:
        """提交任务。"""
        return await orchestrator.submit_task(task)

    @router.delete("/tasks/{task_id}/data", response_model=dict[str, int])
    async def delete_task_data(task_id: str) -> dict[str, int]:
        """按任务清理所有关联数据（软删除）。"""
        return await orchestrator.delete_task_data(task_id)

    @router.get("/admin/retention/stats", response_model=dict[str, int])
    async def retention_stats(
        grace_days: int = Query(default=7, ge=1),
    ) -> dict[str, int]:
        """清理统计接口。"""
        return await orchestrator.store.get_retention_stats(grace_days=grace_days)

    return router
