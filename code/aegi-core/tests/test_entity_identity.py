# Author: msq
"""Entity identity versioning tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from aegi_core.api.deps import get_db_session, get_neo4j_store
from aegi_core.api.routes.entity_identity import router
from aegi_core.services.entity_disambiguator import (
    MergeGroup,
    record_merge_identity_action,
    rollback_identity_action,
)


class _DummySession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        return None


class _DummyNeo4j:
    def __init__(self) -> None:
        self.edges: list[tuple[str, str, str, list[dict]]] = []

    async def upsert_edges(
        self,
        source_label: str,
        target_label: str,
        rel_type: str,
        edges: list[dict],
    ) -> None:
        self.edges.append((source_label, target_label, rel_type, edges))


@dataclass
class _DummyIdentityAction:
    uid: str
    case_uid: str
    action_type: str
    entity_uids: list[str]
    result_entity_uid: str
    reason: str
    performed_by: str
    approved: bool
    approved_by: str | None
    status: str
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime


@pytest.mark.asyncio
async def test_record_merge_identity_action_builds_merge_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def _fake_create_identity_action(session, payload):
        captured["payload"] = payload
        now = datetime.now(timezone.utc)
        return _DummyIdentityAction(
            uid="eia_1",
            case_uid=payload.case_uid,
            action_type=payload.action_type,
            entity_uids=payload.entity_uids,
            result_entity_uid=payload.result_entity_uid,
            reason=payload.reason,
            performed_by=payload.performed_by,
            approved=payload.approved,
            approved_by=payload.approved_by,
            status="pending",
            rejection_reason=None,
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(
        "aegi_core.services.entity_disambiguator.create_identity_action",
        _fake_create_identity_action,
    )

    group = MergeGroup(
        canonical_uid="entity_a",
        canonical_label="China",
        alias_uids=["entity_b"],
        alias_labels=["PRC"],
        confidence=0.95,
        explanation="rule-match",
    )

    row = await record_merge_identity_action(
        _DummySession(),
        case_uid="case_1",
        merge_group=group,
    )

    payload = captured["payload"]
    assert payload.action_type == "merge"
    assert payload.entity_uids == ["entity_a", "entity_b"]
    assert row.uid == "eia_1"


@pytest.mark.asyncio
async def test_rollback_identity_action_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    expected = _DummyIdentityAction(
        uid="eia_rb",
        case_uid="case_1",
        action_type="merge",
        entity_uids=["e1", "e2"],
        result_entity_uid="e1",
        reason="rollback",
        performed_by="expert",
        approved=False,
        approved_by=None,
        status="rolled_back",
        rejection_reason=None,
        created_at=now,
        updated_at=now,
    )

    async def _fake_rollback(session, action_uid):
        assert action_uid == "eia_rb"
        return expected

    monkeypatch.setattr(
        "aegi_core.services.entity_disambiguator.rollback_identity_action_db",
        _fake_rollback,
    )

    row = await rollback_identity_action(_DummySession(), "eia_rb")
    assert row.status == "rolled_back"


@pytest.mark.asyncio
async def test_entity_identity_approval_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    pending_row = _DummyIdentityAction(
        uid="eia_pending",
        case_uid="case_1",
        action_type="merge",
        entity_uids=["e1", "e2"],
        result_entity_uid="e1",
        reason="needs review",
        performed_by="llm",
        approved=False,
        approved_by=None,
        status="pending",
        rejection_reason=None,
        created_at=now,
        updated_at=now,
    )

    async def _fake_pending(session, limit=100):
        return [pending_row]

    async def _fake_approve(session, uid, approved_by):
        assert uid == "eia_pending"
        return _DummyIdentityAction(
            uid=uid,
            case_uid="case_1",
            action_type="merge",
            entity_uids=["e1", "e2"],
            result_entity_uid="e1",
            reason="approved",
            performed_by="llm",
            approved=True,
            approved_by=approved_by,
            status="approved",
            rejection_reason=None,
            created_at=now,
            updated_at=now,
        )

    async def _fake_reject(session, uid, rejected_by, reason):
        assert uid == "eia_pending"
        return _DummyIdentityAction(
            uid=uid,
            case_uid="case_1",
            action_type="merge",
            entity_uids=["e1", "e2"],
            result_entity_uid="e1",
            reason="rejected",
            performed_by="llm",
            approved=False,
            approved_by=rejected_by,
            status="rejected",
            rejection_reason=reason,
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(
        "aegi_core.api.routes.entity_identity.list_pending_identity_actions",
        _fake_pending,
    )
    monkeypatch.setattr(
        "aegi_core.api.routes.entity_identity.approve_identity_action",
        _fake_approve,
    )
    monkeypatch.setattr(
        "aegi_core.api.routes.entity_identity.reject_identity_action",
        _fake_reject,
    )

    app = FastAPI()
    app.include_router(router)

    session = _DummySession()
    neo4j = _DummyNeo4j()

    async def _override_db():
        yield session

    def _override_neo4j():
        return neo4j

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_neo4j_store] = _override_neo4j

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        pending_resp = await client.get("/api/entity-identity/pending")
        assert pending_resp.status_code == 200
        assert pending_resp.json()["total"] == 1

        approve_resp = await client.post(
            "/api/entity-identity/eia_pending/approve",
            json={"approved_by": "expert_1"},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["item"]["status"] == "approved"

        reject_resp = await client.post(
            "/api/entity-identity/eia_pending/reject",
            json={"rejected_by": "expert_2", "reason": "insufficient evidence"},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["item"]["status"] == "rejected"

    assert neo4j.edges, "approve endpoint should project SAME_AS edges"
