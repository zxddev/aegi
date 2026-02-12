# AEGI Project Overview

## Purpose
Intelligence analysis engine (情报分析引擎) — Python/FastAPI backend integrating with OpenClaw (Node.js Agent Runtime) to serve intelligence analysts via a Vue frontend (not yet built).

## Tech Stack
- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic
- PostgreSQL (8710), LiteLLM (8713), Neo4j (8715), Qdrant (8716/8717), MinIO (8711)
- OpenClaw Gateway (4800) — WebSocket integration
- Build: setuptools, uv for dependency management
- Dev: pytest, pytest-asyncio, ruff

## Project Root
`/home/user/workspace/gitcode/aegi/code/` (Serena project root)

## Key Directories
- `aegi-core/` — main Python package
  - `src/aegi_core/api/` — FastAPI app + routes
  - `src/aegi_core/services/` — business logic
  - `src/aegi_core/db/` — SQLAlchemy models
  - `src/aegi_core/infra/` — external service clients (LLM, MinIO, Neo4j, Qdrant)
  - `src/aegi_core/openclaw/` — OpenClaw Gateway integration (new)
  - `src/aegi_core/ws/` — Frontend WebSocket protocol (new)
  - `src/aegi_core/settings.py` — pydantic-settings with AEGI_ env prefix
- `aegi-mcp-gateway/` — MCP gateway service
- `openspec/` — Change specs

## Settings
All via env vars with `AEGI_` prefix. See `settings.py`.

## Conventions
- Author: msq
- Type hints everywhere, Pydantic models for schemas
- `from __future__ import annotations` in new files
- Docstrings: Google-style or brief module-level
- Async-first (asyncpg, async SQLAlchemy)
