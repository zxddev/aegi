# Author: msq
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from aegi_core.settings import settings

_engine: AsyncEngine | None = None


def _build_engine() -> AsyncEngine:
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if settings.db_use_null_pool:
        kwargs["poolclass"] = NullPool
    return create_async_engine(settings.postgres_dsn_async, **kwargs)


def get_engine() -> AsyncEngine:
    """返回共享引擎实例，首次调用时延迟创建。"""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def reset_engine() -> None:
    """重置引擎（测试用）。"""
    global _engine
    _engine = None


class _EngineProxy:
    """向后兼容代理，使 ``ENGINE.xxx`` 等价于 ``get_engine().xxx``。"""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_engine(), name)


ENGINE = _EngineProxy()  # type: ignore[assignment]
