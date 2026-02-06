# AEGI Foundry v0.2 (P0) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stand up an AEGI monorepo (`code/`) with a minimal, runnable P0 that closes the evidence loop end-to-end:
`URL/Search -> Archive (ArtifactVersion) -> Parse -> Chunk(anchor_set) -> Evidence -> SourceClaim -> Assertion`, with Action-only writes + audit traces.

**Architecture:** Modular monolith split into two services inside this repo:
- `code/aegi-mcp-gateway/`: tool plane (governed outbound access + adapter/proxy to SearxNG/ArchiveBox/Unstructured/Tika) + tool audit.
- `code/aegi-core/`: control/data plane (cases, evidence chain, extraction jobs, action log) + uses the gateway for all external calls.

**Tech Stack (P0 defaults):**
- Python 3.12+, `uv`, FastAPI, Pydantic v2, httpx
- Postgres (authoritative store) + Alembic migrations
- MinIO (artifact object storage) via S3-compatible client (boto3)
- Pytest, Ruff

**Repo layout note:** Both services use the `src/` layout.
- `aegi-core` package root: `code/aegi-core/src/aegi_core/`
- `aegi-mcp-gateway` package root: `code/aegi-mcp-gateway/src/aegi_mcp_gateway/`

To run tests / uvicorn after switching to `src/`, install each service once:

```bash
cd code/aegi-core && uv sync --dev && uv pip install -e .
cd code/aegi-mcp-gateway && uv sync --dev && uv pip install -e .
```

---

## Repo Conventions (P0)

1) Never copy AGPL code into `code/aegi-core/` or `code/aegi-mcp-gateway/`.
   - If an upstream project is AGPL (e.g. SearxNG/MISP/IntelOwl/IntelMQ/Cortex), run it as an external service and integrate only via HTTP through the gateway.
2) All writes that change state happen via an `Action` record (Action-only writes).
3) All external calls must go through `aegi-mcp-gateway` and produce a `tool_trace` record.
4) Offline regression first: tests should run without calling the internet.

---

### Task 1: Create Monorepo Service Skeletons

**Files:**
- Create: `code/aegi-core/pyproject.toml`
- Create: `code/aegi-core/src/aegi_core/api/main.py`
- Create: `code/aegi-core/src/aegi_core/__init__.py`
- Create: `code/aegi-core/tests/test_health.py`
- Create: `code/aegi-mcp-gateway/pyproject.toml`
- Create: `code/aegi-mcp-gateway/src/aegi_mcp_gateway/api/main.py`
- Create: `code/aegi-mcp-gateway/src/aegi_mcp_gateway/__init__.py`
- Create: `code/aegi-mcp-gateway/tests/test_health.py`

**Step 1: Add `aegi-core` `pyproject.toml`**

Create `code/aegi-core/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "aegi-core"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.7",
  "httpx>=0.27",
]

[tool.uv]
dev-dependencies = [
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "ruff>=0.5",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

**Step 2: Add minimal FastAPI app + health route**

Create `code/aegi-core/src/aegi_core/api/main.py`:

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="aegi-core", version="0.0.0")

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "aegi-core"}

    return app


app = create_app()
```

Create `code/aegi-core/src/aegi_core/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.0.0"
```

**Step 3: Write a failing test (then make it pass)**

Create `code/aegi-core/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from aegi_core.api.main import app


def test_health_ok() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
```

**Step 4: Run tests**

Run:

```bash
cd code/aegi-core
uv sync --dev
uv pip install -e .
uv run pytest -q
```

Expected: PASS.

**Step 5: Repeat for `aegi-mcp-gateway`**

Create `code/aegi-mcp-gateway/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "aegi-mcp-gateway"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.7",
  "httpx>=0.27",
]

[tool.uv]
dev-dependencies = [
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "ruff>=0.5",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

Create `code/aegi-mcp-gateway/src/aegi_mcp_gateway/api/main.py`:

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="aegi-mcp-gateway", version="0.0.0")

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "aegi-mcp-gateway"}

    return app


app = create_app()
```

Create `code/aegi-mcp-gateway/src/aegi_mcp_gateway/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.0.0"
```

Create `code/aegi-mcp-gateway/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from aegi_mcp_gateway.api.main import app


def test_health_ok() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
```

Run:

```bash
cd code/aegi-mcp-gateway
uv sync --dev
uv pip install -e .
uv run pytest -q
```

Expected: PASS.

---

### Task 2: Add Shared Dev Compose (Postgres + MinIO)

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`

**Step 1: Add `.env.example`**

Create `.env.example`:

```bash
AEGI_PORT_BASE=8700

POSTGRES_USER=aegi
POSTGRES_PASSWORD=aegi
POSTGRES_DB=aegi

MINIO_ROOT_USER=aegi
MINIO_ROOT_PASSWORD=aegi-minio-password
MINIO_PORT=8711
MINIO_CONSOLE_PORT=8712

POSTGRES_PORT=8710

AEGI_POSTGRES_DSN_ASYNC=postgresql+asyncpg://aegi:aegi@localhost:8710/aegi
AEGI_POSTGRES_DSN_SYNC=postgresql+psycopg://aegi:aegi@localhost:8710/aegi

AEGI_S3_ENDPOINT_URL=http://localhost:8711
AEGI_S3_ACCESS_KEY=aegi
AEGI_S3_SECRET_KEY=aegi-minio-password
AEGI_S3_BUCKET=aegi-artifacts

AEGI_CORE_PORT=8700
AEGI_MCP_GATEWAY_PORT=8704

AEGI_MCP_GATEWAY_BASE_URL=http://localhost:8704
```

**Step 2: Add `docker-compose.yml`**

Create `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "${POSTGRES_PORT:-8710}:5432"
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-aegi}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-aegi}
      POSTGRES_DB: ${POSTGRES_DB:-aegi}
    volumes:
      - aegi-postgres:/var/lib/postgresql/data

  minio:
    image: minio/minio:RELEASE.2025-01-20T14-49-07Z
    command: ["server", "/data", "--console-address", ":9001"]
    ports:
      - "${MINIO_PORT:-8711}:9000"
      - "${MINIO_CONSOLE_PORT:-8712}:9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-aegi}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-aegi-minio-password}
    volumes:
      - aegi-minio:/data

volumes:
  aegi-postgres:
  aegi-minio:
```

**Step 3: Verify services start**

Run:

```bash
cp .env.example .env
docker compose up -d
docker compose ps
```

Expected: `postgres` and `minio` are `Up`.

---

### Task 3: Add `aegi-core` Settings + DB Session + Migrations

**Files:**
- Modify: `code/aegi-core/pyproject.toml`
- Create: `code/aegi-core/aegi_core/settings.py`
- Create: `code/aegi-core/aegi_core/db/session.py`
- Create: `code/aegi-core/aegi_core/db/base.py`
- Create: `code/aegi-core/alembic.ini`
- Create: `code/aegi-core/alembic/env.py`
- Create: `code/aegi-core/alembic/script.py.mako`
- Create: `code/aegi-core/alembic/versions/.gitkeep`
- Create: `code/aegi-core/tests/test_db_smoke.py`

**Step 1: Add DB deps**

Update `code/aegi-core/pyproject.toml` dependencies to include:

```toml
  "sqlalchemy>=2.0",
  "alembic>=1.13",
  "asyncpg>=0.29",
  "psycopg[binary]>=3.2",
  "pydantic-settings>=2.3",
```

**Step 2: Settings**

Create `code/aegi-core/src/aegi_core/settings.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AEGI_", case_sensitive=False)

    postgres_dsn_async: str = "postgresql+asyncpg://aegi:aegi@localhost:8710/aegi"
    postgres_dsn_sync: str = "postgresql+psycopg://aegi:aegi@localhost:8710/aegi"
    mcp_gateway_base_url: str = "http://localhost:8704"


settings = Settings()
```

**Step 3: DB session**

Create `code/aegi-core/src/aegi_core/db/session.py`:

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from aegi_core.settings import settings


def create_engine() -> AsyncEngine:
    return create_async_engine(settings.postgres_dsn_async, pool_pre_ping=True)


ENGINE = create_engine()

AsyncSessionLocal = sessionmaker(bind=ENGINE, class_=AsyncSession, expire_on_commit=False)
```

Create `code/aegi-core/src/aegi_core/db/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

**Step 4: Smoke test DB connectivity**

Create `code/aegi-core/tests/test_db_smoke.py`:

```python
import sqlalchemy as sa

from aegi_core.db.session import ENGINE


async def test_db_select_1() -> None:
    async with ENGINE.connect() as conn:
        result = await conn.execute(sa.text("select 1"))
        assert result.scalar_one() == 1
```

Run:

```bash
docker compose up -d postgres
cd code/aegi-core && uv run pytest -q
```

Expected: PASS.

**Step 5: Initialize Alembic**

Create `code/aegi-core/alembic.ini` (minimal):

```ini
  [alembic]
  script_location = alembic
  prepend_sys_path = src
  sqlalchemy.url = postgresql+psycopg://aegi:aegi@localhost:8710/aegi

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers = console
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `code/aegi-core/alembic/env.py`:

```python
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from aegi_core.db.base import Base
from aegi_core.settings import settings

import aegi_core.db.models  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


config.set_main_option("sqlalchemy.url", settings.postgres_dsn_sync)


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Create `code/aegi-core/alembic/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

---

### Task 4: Implement P0 Data Model (Artifacts/Chunks/Evidence/Claims/Actions)

**Files:**
- Create: `code/aegi-core/aegi_core/db/utils.py`
- Create: `code/aegi-core/aegi_core/db/models/case.py`
- Create: `code/aegi-core/aegi_core/db/models/artifact.py`
- Create: `code/aegi-core/aegi_core/db/models/chunk.py`
- Create: `code/aegi-core/aegi_core/db/models/evidence.py`
- Create: `code/aegi-core/aegi_core/db/models/source_claim.py`
- Create: `code/aegi-core/aegi_core/db/models/assertion.py`
- Create: `code/aegi-core/aegi_core/db/models/action.py`
- Create: `code/aegi-core/aegi_core/db/models/tool_trace.py`
- Create: `code/aegi-core/aegi_core/db/models/__init__.py`
- Create: `code/aegi-core/tests/test_models_import.py`

**Step 1: Add minimal models (SQLAlchemy)**

Create `code/aegi-core/aegi_core/db/models/__init__.py`:

```python
from aegi_core.db.models.action import Action
from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.assertion import Assertion, AssertionSourceClaim
from aegi_core.db.models.case import Case
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.db.models.tool_trace import ToolTrace

__all__ = [
    "Action",
    "ArtifactIdentity",
    "ArtifactVersion",
    "Assertion",
    "AssertionSourceClaim",
    "Case",
    "Chunk",
    "Evidence",
    "SourceClaim",
    "ToolTrace",
]
```

Create `code/aegi-core/aegi_core/db/utils.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
```

Create `code/aegi-core/aegi_core/db/models/case.py`:

```python
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Case(Base):
    __tablename__ = "cases"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    title: Mapped[str] = mapped_column(sa.Text(), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
```

Create `code/aegi-core/aegi_core/db/models/artifact.py`:

```python
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class ArtifactIdentity(Base):
    __tablename__ = "artifact_identities"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(sa.Text())

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )

    versions: Mapped[list["ArtifactVersion"]] = relationship(
        back_populates="artifact_identity", cascade="all, delete-orphan"
    )


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    artifact_identity_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("artifact_identities.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    retrieved_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )

    storage_ref: Mapped[str | None] = mapped_column(sa.Text())
    content_sha256: Mapped[str | None] = mapped_column(sa.String(64))
    content_type: Mapped[str | None] = mapped_column(sa.Text())

    source_meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )

    artifact_identity: Mapped[ArtifactIdentity] = relationship(back_populates="versions")
```

Create `code/aegi-core/aegi_core/db/models/chunk.py`:

```python
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Chunk(Base):
    __tablename__ = "chunks"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    artifact_version_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("artifact_versions.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    ordinal: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    text: Mapped[str] = mapped_column(sa.Text(), nullable=False)

    anchor_set: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    anchor_health: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
```

Create `code/aegi-core/aegi_core/db/models/evidence.py`:

```python
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Evidence(Base):
    __tablename__ = "evidence"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64), sa.ForeignKey("cases.uid", ondelete="CASCADE"), index=True
    )

    artifact_version_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("artifact_versions.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("chunks.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    license_note: Mapped[str | None] = mapped_column(sa.Text())

    pii_flags: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    retention_policy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
```

Create `code/aegi-core/aegi_core/db/models/source_claim.py`:

```python
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class SourceClaim(Base):
    __tablename__ = "source_claims"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64), sa.ForeignKey("cases.uid", ondelete="CASCADE"), index=True
    )

    artifact_version_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("artifact_versions.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_uid: Mapped[str] = mapped_column(
        sa.String(64), sa.ForeignKey("chunks.uid", ondelete="CASCADE"), index=True
    )
    evidence_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("evidence.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    quote: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    selectors: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    attributed_to: Mapped[str | None] = mapped_column(sa.Text())
    modality: Mapped[str | None] = mapped_column(sa.String(32))

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
```

Create `code/aegi-core/aegi_core/db/models/assertion.py`:

```python
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Assertion(Base):
    __tablename__ = "assertions"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64), sa.ForeignKey("cases.uid", ondelete="CASCADE"), index=True
    )

    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence: Mapped[float | None] = mapped_column(sa.Float())

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )


class AssertionSourceClaim(Base):
    __tablename__ = "assertion_source_claims"

    assertion_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("assertions.uid", ondelete="CASCADE"),
        primary_key=True,
    )
    source_claim_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("source_claims.uid", ondelete="CASCADE"),
        primary_key=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
```

Create `code/aegi-core/aegi_core/db/models/action.py`:

```python
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Action(Base):
    __tablename__ = "actions"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64), sa.ForeignKey("cases.uid", ondelete="CASCADE"), index=True
    )

    action_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(sa.Text())
    rationale: Mapped[str | None] = mapped_column(sa.Text())

    inputs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    outputs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
```

Create `code/aegi-core/aegi_core/db/models/tool_trace.py`:

```python
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class ToolTrace(Base):
    __tablename__ = "tool_traces"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64), sa.ForeignKey("cases.uid", ondelete="CASCADE"), index=True
    )
    action_uid: Mapped[str | None] = mapped_column(
        sa.String(64), sa.ForeignKey("actions.uid", ondelete="SET NULL"), index=True
    )

    tool_name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    request: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    error: Mapped[str | None] = mapped_column(sa.Text())

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
```

**Step 2: Add import smoke test**

Create `code/aegi-core/tests/test_models_import.py`:

```python
def test_models_import() -> None:
    import aegi_core.db.models  # noqa: F401
```

Run:

```bash
cd code/aegi-core && uv run pytest -q
```

Expected: PASS.

**Step 3: Create first migration**

Run (example):

```bash
cd code/aegi-core
export ALEMBIC_CONFIG=alembic.ini
alembic revision --autogenerate -m "init core tables"
alembic upgrade head
```

Expected: migration generated under `code/aegi-core/alembic/versions/` and `alembic upgrade` succeeds.

---

### Task 5: Implement `aegi-mcp-gateway` Tool Proxies (SearxNG + ArchiveBox + Unstructured/Tika)

**Files:**
- Create: `code/aegi-mcp-gateway/aegi_mcp_gateway/settings.py`
- Create: `code/aegi-mcp-gateway/aegi_mcp_gateway/api/routes/tools.py`
- Modify: `code/aegi-mcp-gateway/aegi_mcp_gateway/api/main.py`

**Step 1: Settings**

Create `code/aegi-mcp-gateway/aegi_mcp_gateway/settings.py`:

```python
from pydantic import BaseModel


class Settings(BaseModel):
    allow_domains: list[str] = []
    searxng_base_url: str = "http://localhost:8601"
    archivebox_base_url: str = "http://localhost:8602"
    unstructured_base_url: str = "http://localhost:8603"
    tika_base_url: str = "http://localhost:9998"


settings = Settings()
```

**Step 2: Tools router**

Create `code/aegi-mcp-gateway/aegi_mcp_gateway/api/routes/tools.py`:

```python
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/tools", tags=["tools"])


class MetaSearchRequest(BaseModel):
    q: str
    categories: list[str] | None = None
    language: str | None = None
    safesearch: int | None = None


@router.post("/meta_search")
async def meta_search(req: MetaSearchRequest) -> dict:
    # P0 stub: implement proxy to SearxNG
    return {"ok": False, "error": "not_implemented"}
```

**Step 3: Mount router**

Update `code/aegi-mcp-gateway/aegi_mcp_gateway/api/main.py` to include:

```python
from aegi_mcp_gateway.api.routes.tools import router as tools_router
...
app.include_router(tools_router)
```

**Step 4: Write tests for stub contract**

Create `code/aegi-mcp-gateway/tests/test_tools_contract.py`:

```python
from fastapi.testclient import TestClient

from aegi_mcp_gateway.api.main import app


def test_meta_search_contract_has_ok_field() -> None:
    client = TestClient(app)
    resp = client.post("/tools/meta_search", json={"q": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert "ok" in body
```

Run:

```bash
cd code/aegi-mcp-gateway && uv run pytest -q
```

Expected: PASS.

---

### Task 6: Wire `aegi-core` -> `aegi-mcp-gateway` Tool Client + ToolTrace

**Files:**
- Create: `code/aegi-core/aegi_core/api/deps.py`
- Create: `code/aegi-core/aegi_core/services/tool_client.py`
- Create: `code/aegi-core/aegi_core/api/routes/ingest.py`
- Modify: `code/aegi-core/aegi_core/api/main.py`
- Create: `code/aegi-core/tests/test_ingest_meta_search_contract.py`

**Step 1: Implement `ToolClient`**

Create `code/aegi-core/aegi_core/services/tool_client.py`:

```python
from __future__ import annotations

import httpx


class ToolClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def meta_search(self, q: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{self._base_url}/tools/meta_search", json={"q": q})
            r.raise_for_status()
            return r.json()
```

**Step 2: Add FastAPI dependency for `ToolClient` (testable, offline-safe)**

Create `code/aegi-core/aegi_core/api/deps.py`:

```python
from aegi_core.services.tool_client import ToolClient
from aegi_core.settings import settings


def get_tool_client() -> ToolClient:
    return ToolClient(base_url=settings.mcp_gateway_base_url)
```

**Step 3: Add `/ingest/meta_search` endpoint**

Create `code/aegi-core/aegi_core/api/routes/ingest.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aegi_core.api.deps import get_tool_client
from aegi_core.services.tool_client import ToolClient


router = APIRouter(prefix="/ingest", tags=["ingest"])


class MetaSearchIn(BaseModel):
    q: str


@router.post("/meta_search")
async def ingest_meta_search(
    body: MetaSearchIn,
    tool: ToolClient = Depends(get_tool_client),
) -> dict:
    return await tool.meta_search(q=body.q)
```

Mount it in `code/aegi-core/aegi_core/api/main.py`.

Example update (keep existing `/health` route):

```python
from aegi_core.api.routes.ingest import router as ingest_router
...
app.include_router(ingest_router)
```

**Step 4: Contract test (no real network calls)**

Create `code/aegi-core/tests/test_ingest_meta_search_contract.py`:

```python
from fastapi.testclient import TestClient

from aegi_core.api.deps import get_tool_client
from aegi_core.api.main import app


class _FakeToolClient:
    async def meta_search(self, q: str) -> dict:
        return {"ok": True, "tool": "meta_search", "q": q, "results": []}


def test_ingest_meta_search_contract() -> None:
    app.dependency_overrides[get_tool_client] = lambda: _FakeToolClient()
    try:
        client = TestClient(app)
        resp = client.post("/ingest/meta_search", json={"q": "example"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["q"] == "example"
    finally:
        app.dependency_overrides.clear()
```

Run:

```bash
cd code/aegi-core && uv run pytest -q
```

Expected: PASS.

---

## Follow-ups (separate plan files)

1) AEGI Workbench UI (`code/aegi-web/`) plan
2) Full ingestion pipeline: ArchiveBox snapshot -> MinIO write -> Unstructured/Tika parse -> chunking + anchors
3) SourceClaim extraction + fusion + conflict UI
4) MISP/OpenCTI import/export mapping
