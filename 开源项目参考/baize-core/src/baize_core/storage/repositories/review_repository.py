"""审查请求 Repository。

负责人工审查请求（Review Request）的数据库操作。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from baize_core.schemas.review_request import (
    ReviewCreateRequest,
    ReviewRequest,
    ReviewStatus,
)
from baize_core.storage import models


@dataclass
class ReviewRepository:
    """审查请求 Repository。

    Attributes:
        session_factory: SQLAlchemy 异步会话工厂
    """

    session_factory: async_sessionmaker[AsyncSession]

    async def create(self, decision: ReviewCreateRequest) -> ReviewRequest:
        """创建审查请求。

        Args:
            decision: 审查创建请求

        Returns:
            审查请求
        """
        review_id = f"review_{uuid4().hex}"
        resume_token = f"resume_{uuid4().hex}"
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            session.add(
                models.ReviewRequestModel(
                    review_id=review_id,
                    task_id=decision.task_id,
                    status=ReviewStatus.PENDING.value,
                    reason=decision.reason,
                    resume_token=resume_token,
                    created_at=now,
                    decided_at=None,
                )
            )
            await session.commit()
        return ReviewRequest(
            review_id=review_id,
            task_id=decision.task_id,
            status=ReviewStatus.PENDING,
            reason=decision.reason,
            resume_token=resume_token,
            created_at=now,
            decided_at=None,
        )

    async def get(self, review_id: str) -> ReviewRequest:
        """读取审查请求。

        Args:
            review_id: 审查 ID

        Returns:
            审查请求

        Raises:
            ValueError: 审查不存在
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.ReviewRequestModel).where(
                    models.ReviewRequestModel.review_id == review_id
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                raise ValueError(f"审查不存在: {review_id}")
            return ReviewRequest(
                review_id=record.review_id,
                task_id=record.task_id,
                status=ReviewStatus(record.status),
                reason=record.reason,
                resume_token=record.resume_token,
                created_at=record.created_at,
                decided_at=record.decided_at,
            )

    async def approve(self, review_id: str) -> ReviewRequest:
        """通过审查。

        Args:
            review_id: 审查 ID

        Returns:
            审查请求
        """
        return await self._decide(review_id, ReviewStatus.APPROVED)

    async def reject(self, review_id: str, reason: str | None) -> ReviewRequest:
        """拒绝审查。

        Args:
            review_id: 审查 ID
            reason: 拒绝原因

        Returns:
            审查请求
        """
        return await self._decide(review_id, ReviewStatus.REJECTED, reason=reason)

    async def _decide(
        self,
        review_id: str,
        status: ReviewStatus,
        *,
        reason: str | None = None,
    ) -> ReviewRequest:
        """更新审查状态。

        Args:
            review_id: 审查 ID
            status: 目标状态
            reason: 原因（可选）

        Returns:
            审查请求

        Raises:
            ValueError: 审查不存在
        """
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.ReviewRequestModel).where(
                    models.ReviewRequestModel.review_id == review_id
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                raise ValueError(f"审查不存在: {review_id}")
            record.status = status.value
            record.reason = reason
            record.decided_at = now
            await session.commit()
            return ReviewRequest(
                review_id=record.review_id,
                task_id=record.task_id,
                status=ReviewStatus(record.status),
                reason=record.reason,
                resume_token=record.resume_token,
                created_at=record.created_at,
                decided_at=record.decided_at,
            )
