# Author: msq

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from time import monotonic

from fastapi import APIRouter, Depends
from fastapi import Depends as FastApiDepends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_tool_client
from aegi_core.api.errors import AegiHTTPError
from aegi_core.api.errors import not_found
from aegi_core.db.models.action import Action
from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.assertion import Assertion
from aegi_core.db.models.case import Case
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.judgment import Judgment
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.db.models.tool_trace import ToolTrace
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
    case_uid = f"case_{uuid4().hex}"
    action_uid = f"act_{uuid4().hex}"

    case = Case(uid=case_uid, title=body.title)
    action = Action(
        uid=action_uid,
        case_uid=case_uid,
        action_type="case.create",
        actor_id=body.actor_id,
        rationale=body.rationale,
        inputs=body.model_dump(exclude_none=True),
        outputs={"case_uid": case_uid},
    )

    session.add(case)
    await session.flush()
    session.add(action)
    await session.commit()

    return {"case_uid": case_uid, "title": body.title, "action_uid": action_uid}


@router.get("/{case_uid}")
async def get_case(
    case_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)

    return {"case_uid": case.uid, "title": case.title}


@router.get("/{case_uid}/artifacts")
async def list_case_artifacts(
    case_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await session.execute(
        sa.select(ArtifactVersion).where(ArtifactVersion.case_uid == case_uid)
    )
    items = []
    for av in result.scalars().all():
        items.append(
            {
                "artifact_version_uid": av.uid,
                "content_sha256": av.content_sha256,
                "storage_ref": av.storage_ref,
            }
        )
    return {"items": items}


@router.post("/{case_uid}/tools/archive_url")
async def call_tool_archive_url(
    case_uid: str,
    body: ToolArchiveUrlIn,
    session: AsyncSession = Depends(get_db_session),
    tool: ToolClient = FastApiDepends(get_tool_client),
) -> dict:
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)

    action_uid = f"act_{uuid4().hex}"
    action = Action(
        uid=action_uid,
        case_uid=case_uid,
        action_type="tool.archive_url",
        actor_id=body.actor_id,
        rationale=body.rationale,
        inputs=body.model_dump(exclude_none=True),
        outputs={},
    )
    session.add(action)
    await session.flush()

    start = monotonic()
    tool_trace_uid = f"tt_{uuid4().hex}"

    try:
        resp = await tool.archive_url(url=body.url)
        duration_ms = int((monotonic() - start) * 1000)

        policy = resp.get("policy") if isinstance(resp, dict) else {}
        if not isinstance(policy, dict):
            policy = {}

        trace = ToolTrace(
            uid=tool_trace_uid,
            case_uid=case_uid,
            action_uid=action_uid,
            tool_name="archive_url",
            request={"url": body.url},
            response=resp if isinstance(resp, dict) else {"raw": resp},
            status="ok" if isinstance(resp, dict) else "unknown",
            duration_ms=duration_ms,
            error=None,
            policy=policy,
        )
        session.add(trace)

        action.outputs = {"tool_trace_uid": tool_trace_uid}
        await session.commit()

        return {"action_uid": action_uid, "tool_trace_uid": tool_trace_uid, "response": resp}
    except AegiHTTPError as exc:
        duration_ms = int((monotonic() - start) * 1000)

        trace = ToolTrace(
            uid=tool_trace_uid,
            case_uid=case_uid,
            action_uid=action_uid,
            tool_name="archive_url",
            request={"url": body.url},
            response={"error_code": exc.error_code, "message": exc.message, "details": exc.details},
            status="denied" if exc.status_code in (403, 429) else "error",
            duration_ms=duration_ms,
            error=exc.error_code,
            policy={
                "allowed": False,
                "reason": exc.error_code,
                "details": exc.details,
            },
        )
        session.add(trace)

        action.outputs = {"tool_trace_uid": tool_trace_uid, "error_code": exc.error_code}
        await session.commit()
        raise


@router.post("/{case_uid}/fixtures/import", status_code=201)
async def import_fixture(
    case_uid: str,
    body: FixtureImportIn,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    # P0 (fixtures-only): import offline fixtures into the authoritative store.
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)

    manifest_path = _FIXTURES_ROOT / "manifest.json"
    if not manifest_path.exists():
        raise AegiHTTPError(
            500,
            "fixtures_not_available",
            "Fixtures manifest not available",
            {"path": str(manifest_path)},
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        fixtures = []

    fixture_item = next(
        (f for f in fixtures if isinstance(f, dict) and f.get("fixture_id") == body.fixture_id),
        None,
    )
    if fixture_item is None:
        raise AegiHTTPError(
            404,
            "fixture_not_found",
            "Fixture not found",
            {"fixture_id": body.fixture_id},
        )

    artifact = fixture_item.get("artifact")
    if not isinstance(artifact, dict):
        raise AegiHTTPError(
            500,
            "fixture_invalid",
            "Fixture artifact metadata invalid",
            {"fixture_id": body.fixture_id},
        )

    artifact_kind = artifact.get("kind")
    rel_artifact_path = artifact.get("path")
    if not isinstance(artifact_kind, str) or not isinstance(rel_artifact_path, str):
        raise AegiHTTPError(
            500,
            "fixture_invalid",
            "Fixture artifact kind/path invalid",
            {"fixture_id": body.fixture_id},
        )

    artifact_path = _FIXTURES_ROOT / rel_artifact_path
    artifact_bytes = artifact_path.read_bytes()
    content_sha256 = hashlib.sha256(artifact_bytes).hexdigest()

    if artifact_kind == "html":
        content_type = "text/html"
    elif artifact_kind == "pdf":
        content_type = "application/pdf"
    else:
        content_type = "application/octet-stream"

    artifact_identity_uid = f"ai_{uuid4().hex}"
    artifact_version_uid = f"av_{uuid4().hex}"

    session.add(ArtifactIdentity(uid=artifact_identity_uid, kind=artifact_kind, canonical_url=None))
    session.add(
        ArtifactVersion(
            uid=artifact_version_uid,
            artifact_identity_uid=artifact_identity_uid,
            case_uid=case_uid,
            storage_ref=f"fixtures://{rel_artifact_path}",
            content_sha256=content_sha256,
            content_type=content_type,
            source_meta={
                "fixture_id": body.fixture_id,
                "domain": fixture_item.get("domain"),
                "artifact_kind": artifact_kind,
            },
        )
    )

    chunks_doc = json.loads(
        ((_FIXTURES_ROOT / fixture_item["chunks_path"]).read_text(encoding="utf-8"))
    )
    chunks_src = chunks_doc.get("chunks")
    if not isinstance(chunks_src, list) or not chunks_src:
        raise AegiHTTPError(
            500,
            "fixture_invalid",
            "Fixture chunks invalid",
            {"fixture_id": body.fixture_id},
        )

    chunk_uids: list[str] = []
    quote_to_chunk_uid: dict[str, str] = {}
    for idx, ch in enumerate(chunks_src):
        if not isinstance(ch, dict):
            continue
        anchor_set = ch.get("anchor_set")
        if not isinstance(anchor_set, list):
            anchor_set = []

        text_quote = None
        for sel in anchor_set:
            if isinstance(sel, dict) and sel.get("type") == "TextQuoteSelector":
                exact = sel.get("exact")
                if isinstance(exact, str) and exact:
                    text_quote = exact
                    quote_to_chunk_uid[exact] = ""
                    break

        chunk_uid = f"chunk_{uuid4().hex}"
        chunk_uids.append(chunk_uid)

        if text_quote is not None:
            quote_to_chunk_uid[text_quote] = chunk_uid

        session.add(
            Chunk(
                uid=chunk_uid,
                artifact_version_uid=artifact_version_uid,
                ordinal=idx,
                text=text_quote or "",
                anchor_set=anchor_set,
                anchor_health={},
            )
        )

    sc_doc = json.loads(
        ((_FIXTURES_ROOT / fixture_item["source_claims_path"]).read_text(encoding="utf-8"))
    )
    sc_src = sc_doc.get("source_claims")
    if not isinstance(sc_src, list) or not sc_src:
        raise AegiHTTPError(
            500,
            "fixture_invalid",
            "Fixture source_claims invalid",
            {"fixture_id": body.fixture_id},
        )

    evidence_uids: list[str] = []
    source_claim_uids: list[str] = []
    fixture_sc_uid_to_uid: dict[str, str] = {}

    default_chunk_uid = chunk_uids[0]

    for sc in sc_src:
        if not isinstance(sc, dict):
            continue
        quote = sc.get("quote")
        if not isinstance(quote, str):
            continue
        selectors = sc.get("selectors")
        if not isinstance(selectors, list):
            selectors = []

        chunk_uid = default_chunk_uid
        for sel in selectors:
            if isinstance(sel, dict) and sel.get("type") == "TextQuoteSelector":
                exact = sel.get("exact")
                if isinstance(exact, str) and exact and exact in quote_to_chunk_uid:
                    mapped = quote_to_chunk_uid.get(exact)
                    if mapped:
                        chunk_uid = mapped
                    break

        evidence_uid = f"ev_{uuid4().hex}"
        source_claim_uid = f"sc_{uuid4().hex}"

        evidence_uids.append(evidence_uid)
        source_claim_uids.append(source_claim_uid)

        session.add(
            Evidence(
                uid=evidence_uid,
                case_uid=case_uid,
                artifact_version_uid=artifact_version_uid,
                chunk_uid=chunk_uid,
                kind="quote",
                license_note=None,
                pii_flags={},
                retention_policy={},
            )
        )
        session.add(
            SourceClaim(
                uid=source_claim_uid,
                case_uid=case_uid,
                artifact_version_uid=artifact_version_uid,
                chunk_uid=chunk_uid,
                evidence_uid=evidence_uid,
                quote=quote,
                selectors=selectors,
                attributed_to=None,
                modality=None,
            )
        )

        fixture_sc_uid = sc.get("source_claim_uid")
        if isinstance(fixture_sc_uid, str) and fixture_sc_uid:
            fixture_sc_uid_to_uid[fixture_sc_uid] = source_claim_uid

    assertions_doc = json.loads(
        ((_FIXTURES_ROOT / fixture_item["assertions_path"]).read_text(encoding="utf-8"))
    )
    assertions_src = assertions_doc.get("assertions")
    if not isinstance(assertions_src, list) or not assertions_src:
        raise AegiHTTPError(
            500,
            "fixture_invalid",
            "Fixture assertions invalid",
            {"fixture_id": body.fixture_id},
        )

    assertion_uids: list[str] = []
    for a in assertions_src:
        if not isinstance(a, dict):
            continue
        fixture_sc_uids = a.get("source_claim_uids")
        if not isinstance(fixture_sc_uids, list):
            fixture_sc_uids = []

        mapped_sc_uids = []
        for uid in fixture_sc_uids:
            if isinstance(uid, str) and uid in fixture_sc_uid_to_uid:
                mapped_sc_uids.append(fixture_sc_uid_to_uid[uid])

        assertion_uid = f"as_{uuid4().hex}"
        assertion_uids.append(assertion_uid)

        session.add(
            Assertion(
                uid=assertion_uid,
                case_uid=case_uid,
                kind="event",
                value={},
                source_claim_uids=mapped_sc_uids,
                confidence=None,
            )
        )

    judgment_uid = f"jd_{uuid4().hex}"
    session.add(
        Judgment(
            uid=judgment_uid,
            case_uid=case_uid,
            title=f"Fixture {body.fixture_id}",
            assertion_uids=assertion_uids,
        )
    )

    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="fixture.import",
            actor_id=body.actor_id,
            rationale=body.rationale,
            inputs=body.model_dump(exclude_none=True),
            outputs={
                "fixture_id": body.fixture_id,
                "artifact_identity_uid": artifact_identity_uid,
                "artifact_version_uid": artifact_version_uid,
                "chunk_uids": chunk_uids,
                "evidence_uids": evidence_uids,
                "source_claim_uids": source_claim_uids,
                "assertion_uids": assertion_uids,
                "judgment_uid": judgment_uid,
            },
        )
    )

    await session.commit()

    return {
        "fixture_id": body.fixture_id,
        "action_uid": action_uid,
        "artifact_identity_uid": artifact_identity_uid,
        "artifact_version_uid": artifact_version_uid,
        "chunk_uids": chunk_uids,
        "evidence_uids": evidence_uids,
        "source_claim_uids": source_claim_uids,
        "assertion_uids": assertion_uids,
        "judgment_uid": judgment_uid,
    }
