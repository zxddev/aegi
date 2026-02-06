# Author: msq
"""KG & ontology API routes.

Source: openspec/changes/knowledge-graph-ontology-evolution/design.md (API Contract)
Evidence:
  - POST /cases/{case_uid}/kg/build_from_assertions
  - POST /cases/{case_uid}/ontology/upgrade
  - GET /cases/{case_uid}/ontology/{version}/compatibility_report
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from aegi_core.contracts.schemas import AssertionV1
from aegi_core.services import kg_mapper, ontology_versioning

router = APIRouter(tags=["kg"])


class BuildGraphRequest(BaseModel):
    assertions: list[AssertionV1]
    ontology_version: str


class UpgradeRequest(BaseModel):
    from_version: str
    to_version: str
    approved: bool = False


@router.post("/cases/{case_uid}/kg/build_from_assertions")
async def build_from_assertions(case_uid: str, body: BuildGraphRequest) -> dict:
    result = kg_mapper.build_graph(
        body.assertions,
        case_uid=case_uid,
        ontology_version=body.ontology_version,
    )
    if len(result) == 6:
        _, _, _, action, tool_trace, problem = result
        return {"error": problem.model_dump(), "action": action.model_dump()}

    entities, events, relations, action, tool_trace = result
    return {
        "entities": [e.model_dump() for e in entities],
        "events": [e.model_dump() for e in events],
        "relations": [r.model_dump() for r in relations],
        "action": action.model_dump(),
    }


@router.post("/cases/{case_uid}/ontology/upgrade")
async def ontology_upgrade(case_uid: str, body: UpgradeRequest) -> dict:
    report_or_err, action, tool_trace = ontology_versioning.upgrade_ontology(
        case_uid=case_uid,
        from_version=body.from_version,
        to_version=body.to_version,
        approved=body.approved,
    )
    return {
        "result": report_or_err.model_dump(),
        "action": action.model_dump(),
    }


@router.get("/cases/{case_uid}/ontology/{version}/compatibility_report")
async def compatibility_report(case_uid: str, version: str, from_version: str = "1.0.0") -> dict:
    report = ontology_versioning.compute_compatibility(from_version, version)
    return {"result": report.model_dump()}
