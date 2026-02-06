"""Repository 基类。

提供所有 Repository 共享的基础设施，包括 session_factory 和通用辅助方法。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _rowcount(result: Any) -> int:
    """获取 rowcount 统计。

    Args:
        result: SQLAlchemy 执行结果

    Returns:
        受影响的行数
    """
    return int(getattr(result, "rowcount", 0) or 0)


@dataclass
class BaseRepository:
    """Repository 基类。

    所有领域 Repository 都应继承此类，共享 session_factory。

    Attributes:
        session_factory: SQLAlchemy 异步会话工厂
    """

    session_factory: async_sessionmaker[AsyncSession]
