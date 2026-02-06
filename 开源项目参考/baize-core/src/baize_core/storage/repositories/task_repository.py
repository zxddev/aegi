"""任务 Repository。

负责任务（Task）相关的数据库操作。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from baize_core.schemas.task import TaskResponse, TaskSpec
from baize_core.storage import models


@dataclass
class TaskRepository:
    """任务 Repository。

    Attributes:
        session_factory: SQLAlchemy 异步会话工厂
    """

    session_factory: async_sessionmaker[AsyncSession]

    async def create(self, task: TaskSpec) -> TaskResponse:
        """创建任务记录。

        Args:
            task: 任务规范

        Returns:
            任务响应
        """
        async with self.session_factory() as session:
            record = models.TaskModel(
                task_id=task.task_id,
                objective=task.objective,
                retention_days=task.retention_days,
                constraints=task.constraints,
                time_window=task.time_window,
                region=task.region,
                sensitivity=task.sensitivity.value,
                created_at=datetime.now(UTC),
            )
            session.add(record)
            await session.commit()
        return TaskResponse(
            task_id=task.task_id, status="accepted", message="任务已进入队列"
        )

    async def get_since(self, cutoff: datetime) -> list[models.TaskModel]:
        """获取指定时间之后的任务。

        Args:
            cutoff: 截止时间

        Returns:
            任务列表
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.TaskModel).where(models.TaskModel.created_at >= cutoff)
            )
            return list(result.scalars().all())
