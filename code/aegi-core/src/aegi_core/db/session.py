# Author: msq
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from aegi_core.settings import settings


def create_engine() -> AsyncEngine:
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if settings.db_use_null_pool:
        kwargs["poolclass"] = NullPool
    return create_async_engine(settings.postgres_dsn_async, **kwargs)


ENGINE = create_engine()
