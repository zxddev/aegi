# Author: msq
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_tool_client
from aegi_core.services import case_service, fixture_import_service, tool_archive_service
from aegi_core.services.tool_client import ToolClient

router = APIRouter(prefix="/cases", tags=["cases"])

_FIXTURES_ROOT = Path(__file__).resolve().parents[4] / "tests" / "fixtures"


class CaseCreateIn(BaseModel):
    title: str
    actor_id: str | None = None
    rationale: str | None = None


class FixtureImportIn(BaseModel):
    fixture_id: str
    actor_id: str | None = None
    rationale: str | None = None


class ToolArchiveUrlIn(BaseModel):
    url: str
    actor_id: str | None = None
    rationale: str | None = None


@router.post("", status_code=201)
async def create_case(
    body: CaseCreateIn,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await case_service.create_case(
        session,
        title=body.title,
        actor_id=body.actor_id,
        rationale=body.rationale,
        inputs=body.model_dump(exclude_none=True),
    )


@router.get("/{case_uid}")
async def get_case(
    case_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await case_service.get_case(session, case_uid=case_uid)


@router.get("/{case_uid}/artifacts")
async def list_case_artifacts(
    case_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await case_service.list_case_artifacts(session, case_uid=case_uid)


@router.post("/{case_uid}/tools/archive_url")
async def call_tool_archive_url(
    case_uid: str,
    body: ToolArchiveUrlIn,
    session: AsyncSession = Depends(get_db_session),
    tool: ToolClient = Depends(get_tool_client),
) -> dict:
    return await tool_archive_service.call_tool_archive_url(
        session,
        tool,
        case_uid=case_uid,
        url=body.url,
        actor_id=body.actor_id,
        rationale=body.rationale,
        inputs=body.model_dump(exclude_none=True),
    )


@router.post("/{case_uid}/fixtures/import", status_code=201)
async def import_fixture(
    case_uid: str,
    body: FixtureImportIn,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await fixture_import_service.import_fixture(
        session,
        case_uid=case_uid,
        fixture_id=body.fixture_id,
        actor_id=body.actor_id,
        rationale=body.rationale,
        inputs=body.model_dump(exclude_none=True),
        fixtures_root=_FIXTURES_ROOT,
    )
