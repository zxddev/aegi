"""HITL 审查契约。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    """审查状态。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewRequest(BaseModel):
    """审查请求。"""

    review_id: str
    task_id: str | None = None
    status: ReviewStatus
    reason: str | None = None
    resume_token: str
    created_at: datetime
    decided_at: datetime | None = None


class ReviewDecisionInput(BaseModel):
    """审查决策输入。"""

    reason: str | None = None


class ReviewCreateRequest(BaseModel):
    """审查创建请求。"""

    task_id: str | None = None
    reason: str | None = None


class ReviewResponse(BaseModel):
    """审查响应。"""

    review: ReviewRequest = Field(...)
