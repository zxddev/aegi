"""审查接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from baize_core.schemas.review_request import (
    ReviewCreateRequest,
    ReviewDecisionInput,
    ReviewRequest,
)


def get_router(orchestrator: Any) -> APIRouter:
    """审查相关路由。"""
    router = APIRouter()

    @router.post("/reviews", response_model=ReviewRequest)
    async def create_review(payload: ReviewCreateRequest) -> ReviewRequest:
        """创建审查请求。"""
        return await orchestrator.create_review(payload)

    @router.get("/reviews/{review_id}", response_model=ReviewRequest)
    async def get_review(review_id: str) -> ReviewRequest:
        """获取审查状态。"""
        return await orchestrator.get_review(review_id)

    @router.post("/reviews/{review_id}/approve", response_model=ReviewRequest)
    async def approve_review(
        review_id: str, payload: ReviewDecisionInput
    ) -> ReviewRequest:
        """通过审查。"""
        return await orchestrator.approve_review(review_id, payload)

    @router.post("/reviews/{review_id}/reject", response_model=ReviewRequest)
    async def reject_review(
        review_id: str, payload: ReviewDecisionInput
    ) -> ReviewRequest:
        """拒绝审查。"""
        return await orchestrator.reject_review(review_id, payload)

    return router
