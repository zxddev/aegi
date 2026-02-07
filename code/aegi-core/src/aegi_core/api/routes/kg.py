# Author: msq
"""KG & ontology API routes.

Source: openspec/changes/knowledge-graph-ontology-evolution/design.md (API Contract)
Evidence:
  - POST /cases/{case_uid}/kg/build_from_assertions
  - POST /cases/{case_uid}/ontology/upgrade
  - GET /cases/{case_uid}/ontology/{version}/compatibility_report
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_neo4j_store
from aegi_core.contracts.schemas import AssertionV1
from aegi_core.db.models.action import Action
from aegi_core.infra.neo4j_store import Neo4jStore
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
async def build_from_assertions(
    case_uid: str,
    body: BuildGraphRequest,
    session: AsyncSession = Depends(get_db_session),
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> dict:
    result = kg_mapper.build_graph(
        body.assertions,
        case_uid=case_uid,
        ontology_version=body.ontology_version,
    )

    if len(result) == 6:
        _, _, _, svc_action, svc_trace, problem = result
        action_uid = f"act_{uuid4().hex}"
        session.add(
            Action(
                uid=action_uid,
                case_uid=case_uid,
                action_type="kg.build",
                inputs=svc_action.inputs,
                outputs=svc_action.outputs,
                trace_id=svc_action.trace_id,
            )
        )
        await session.commit()
        return {"error": problem.model_dump(), "action_uid": action_uid}

    entities, events, relations, svc_action, svc_trace = result
    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="kg.build",
            inputs=svc_action.inputs,
            outputs=svc_action.outputs,
            trace_id=svc_action.trace_id,
        )
    )
    await session.commit()

    # 持久化到 Neo4j（MERGE 语义，天然幂等，支持增量更新）
    await neo4j.upsert_nodes(
        "Entity",
        [
            {
                "uid": e.uid,
                "name": e.label,
                "type": e.entity_type,
                "case_uid": e.case_uid,
            }
            for e in entities
        ],
    )
    await neo4j.upsert_nodes(
        "Event",
        [
            {
                "uid": e.uid,
                "label": e.label,
                "type": e.event_type,
                "case_uid": e.case_uid,
                "timestamp_ref": e.timestamp_ref,
            }
            for e in events
        ],
    )
    for r in relations:
        src_is_entity = any(e.uid == r.source_entity_uid for e in entities)
        tgt_is_entity = any(e.uid == r.target_entity_uid for e in entities)
        await neo4j.upsert_edges(
            "Entity" if src_is_entity else "Event",
            "Entity" if tgt_is_entity else "Event",
            r.relation_type.upper(),
            [
                {
                    "source_uid": r.source_entity_uid,
                    "target_uid": r.target_entity_uid,
                    "properties": r.properties,
                }
            ],
        )

    return {
        "entities": [e.model_dump() for e in entities],
        "events": [e.model_dump() for e in events],
        "relations": [r.model_dump() for r in relations],
        "action_uid": action_uid,
    }


@router.post("/cases/{case_uid}/ontology/upgrade")
async def ontology_upgrade(
    case_uid: str,
    body: UpgradeRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    report_or_err, svc_action, svc_trace = ontology_versioning.upgrade_ontology(
        case_uid=case_uid,
        from_version=body.from_version,
        to_version=body.to_version,
        approved=body.approved,
    )

    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="ontology.upgrade",
            inputs=svc_action.inputs,
            outputs=svc_action.outputs,
            trace_id=svc_action.trace_id,
        )
    )
    await session.commit()

    return {
        "result": report_or_err.model_dump(),
        "action_uid": action_uid,
    }


@router.get("/cases/{case_uid}/ontology/{version}/compatibility_report")
async def compatibility_report(
    case_uid: str, version: str, from_version: str = "1.0.0"
) -> dict:
    report = ontology_versioning.compute_compatibility(from_version, version)
    return {"result": report.model_dump()}
