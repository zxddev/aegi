# Author: msq
"""KG mapping & ontology versioning tests.

Source: openspec/changes/knowledge-graph-ontology-evolution/tasks.md (4.1-4.3)
Evidence:
  - defgeo-kg-001: 稳定 SPO 映射 (design.md fixtures).
  - defgeo-kg-002: 本体升级兼容 (design.md fixtures).
  - defgeo-kg-003: breaking 变更需拒绝自动升级 (design.md fixtures).
  - KG 构建可回放到 Assertion 与 SourceClaim (spec.md acceptance #1).
  - 兼容性报告必须包含 compatible/deprecated/breaking 分类 (spec.md acceptance #2).
  - case pinning 生效，未经审批不得越版本读取 (spec.md acceptance #3).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from aegi_core.api.main import create_app
from aegi_core.contracts.schemas import AssertionV1
from aegi_core.services import ontology_versioning
from aegi_core.services.ontology_versioning import (
    ChangeLevel,
    OntologyVersion,
    reset_registry,
    register_version,
    pin_case,
    get_case_pin,
)

FIXTURES = Path(__file__).parent / "fixtures" / "defense-geopolitics"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name / "kg_scenario.json").read_text())


def _make_assertions(raw: list[dict]) -> list[AssertionV1]:
    return [AssertionV1(**a) for a in raw]


# TestKGMapping 已移除：旧规则引擎 build_graph 已被 GraphRAG pipeline 替代。
# GraphRAG pipeline 测试需要 LLM mock，见 graphrag_pipeline 独立测试。


class TestOntologyVersioning:
    def setup_method(self) -> None:
        reset_registry()

    def test_compatible_upgrade(self) -> None:
        fixture = _load_fixture("defgeo-kg-002")
        for ver, spec in fixture["versions"].items():
            register_version(
                OntologyVersion(
                    version=ver,
                    entity_types=spec["entity_types"],
                    event_types=spec["event_types"],
                    relation_types=spec["relation_types"],
                    created_at=datetime.now(timezone.utc),
                )
            )
        report = ontology_versioning.compute_compatibility("1.0.0", "1.1.0")
        assert not isinstance(report, ontology_versioning.ProblemDetail)
        assert report.overall_level == ChangeLevel.COMPATIBLE
        assert report.auto_upgrade_allowed is True

    def test_breaking_upgrade_denied_without_approval(self) -> None:
        fixture = _load_fixture("defgeo-kg-003")
        for ver, spec in fixture["versions"].items():
            register_version(
                OntologyVersion(
                    version=ver,
                    entity_types=spec["entity_types"],
                    event_types=spec["event_types"],
                    relation_types=spec["relation_types"],
                    created_at=datetime.now(timezone.utc),
                )
            )
        report_or_err, action, tool_trace = ontology_versioning.upgrade_ontology(
            case_uid="case_break",
            from_version="1.0.0",
            to_version="2.0.0",
            approved=False,
        )
        from aegi_core.contracts.errors import ProblemDetail

        assert isinstance(report_or_err, ProblemDetail)
        assert report_or_err.error_code == "upgrade_denied"
        assert action.action_type == "ontology_upgrade"
        assert tool_trace.status == "denied"

    def test_breaking_upgrade_allowed_with_approval(self) -> None:
        fixture = _load_fixture("defgeo-kg-003")
        for ver, spec in fixture["versions"].items():
            register_version(
                OntologyVersion(
                    version=ver,
                    entity_types=spec["entity_types"],
                    event_types=spec["event_types"],
                    relation_types=spec["relation_types"],
                    created_at=datetime.now(timezone.utc),
                )
            )
        report, action, tool_trace = ontology_versioning.upgrade_ontology(
            case_uid="case_break",
            from_version="1.0.0",
            to_version="2.0.0",
            approved=True,
        )
        from aegi_core.services.ontology_versioning import CompatibilityReport

        assert isinstance(report, CompatibilityReport)
        assert report.overall_level == ChangeLevel.BREAKING
        assert tool_trace.status == "ok"
        assert get_case_pin("case_break") == "2.0.0"

    def test_compatibility_report_categories(self) -> None:
        fixture = _load_fixture("defgeo-kg-003")
        for ver, spec in fixture["versions"].items():
            register_version(
                OntologyVersion(
                    version=ver,
                    entity_types=spec["entity_types"],
                    event_types=spec["event_types"],
                    relation_types=spec["relation_types"],
                    created_at=datetime.now(timezone.utc),
                )
            )
        report = ontology_versioning.compute_compatibility("1.0.0", "2.0.0")
        assert not isinstance(report, ontology_versioning.ProblemDetail)
        levels = {c.level for c in report.changes}
        assert ChangeLevel.BREAKING in levels
        assert ChangeLevel.COMPATIBLE in levels

    def test_case_pinning(self) -> None:
        pin_case("case_pin_test", "1.0.0")
        assert get_case_pin("case_pin_test") == "1.0.0"
        pin_case("case_pin_test", "1.1.0")
        assert get_case_pin("case_pin_test") == "1.1.0"

    def test_version_not_found(self) -> None:
        report = ontology_versioning.compute_compatibility("0.0.0", "9.9.9")
        from aegi_core.contracts.errors import ProblemDetail

        assert isinstance(report, ProblemDetail)
        assert report.error_code == "not_found"


class TestKGAPI:
    @pytest.fixture
    def app(self):
        return create_app()

    @pytest.fixture
    async def client(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    async def _create_case(self, client: AsyncClient, title: str = "kg-test") -> str:
        resp = await client.post("/cases", json={"title": title})
        assert resp.status_code == 201
        return resp.json()["case_uid"]

    async def test_build_from_assertions_api(self, client: AsyncClient) -> None:
        case_uid = await self._create_case(client)
        fixture = _load_fixture("defgeo-kg-001")
        resp = await client.post(
            f"/cases/{case_uid}/kg/build_from_assertions",
            json={
                "assertions": fixture["assertions"],
                "ontology_version": "1.0.0",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "entities" in data
        assert len(data["entities"]) == fixture["expected"]["entity_count"]
        assert "action_uid" in data

    async def test_ontology_upgrade_api(self, client: AsyncClient) -> None:
        case_uid = await self._create_case(client)
        reset_registry()
        now = datetime.now(timezone.utc)
        register_version(
            OntologyVersion(
                version="1.0.0",
                entity_types=["actor"],
                event_types=["deployment"],
                relation_types=["participated_in"],
                created_at=now,
            )
        )
        register_version(
            OntologyVersion(
                version="1.1.0",
                entity_types=["actor", "org"],
                event_types=["deployment"],
                relation_types=["participated_in"],
                created_at=now,
            )
        )
        resp = await client.post(
            f"/cases/{case_uid}/ontology/upgrade",
            json={"from_version": "1.0.0", "to_version": "1.1.0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["overall_level"] == "compatible"

    async def test_compatibility_report_api(self, client: AsyncClient) -> None:
        reset_registry()
        now = datetime.now(timezone.utc)
        register_version(
            OntologyVersion(
                version="1.0.0",
                entity_types=["actor"],
                event_types=[],
                relation_types=[],
                created_at=now,
            )
        )
        register_version(
            OntologyVersion(
                version="2.0.0",
                entity_types=[],
                event_types=[],
                relation_types=[],
                created_at=now,
            )
        )
        resp = await client.get(
            "/cases/case_api/ontology/2.0.0/compatibility_report",
            params={"from_version": "1.0.0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["overall_level"] == "breaking"
