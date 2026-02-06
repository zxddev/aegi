# Author: msq
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from aegi_core.settings import settings


def create_engine() -> AsyncEngine:
    # P0: avoid cross-event-loop pool reuse during tests.
    return create_async_engine(
        settings.postgres_dsn_async,
        pool_pre_ping=True,
        poolclass=NullPool,
    )


ENGINE = create_engine()
