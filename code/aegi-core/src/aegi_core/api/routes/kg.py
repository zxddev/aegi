# Author: msq
"""KG 与本体 API 路由。

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

from aegi_core.api.deps import get_db_session, get_llm_client, get_neo4j_store
from aegi_core.contracts.schemas import AssertionV1
from aegi_core.db.models.action import Action
from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.infra.llm_client import LLMClient
from aegi_core.services import ontology_versioning
from aegi_core.services import graphrag_pipeline
from aegi_core.services.entity import EntityV1
from aegi_core.services.entity_disambiguator import (
    disambiguate_entities,
    record_merge_identity_action,
)

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
    llm: LLMClient = Depends(get_llm_client),
) -> dict:
    result = await graphrag_pipeline.extract_and_index(
        body.assertions,
        case_uid=case_uid,
        ontology_version=body.ontology_version,
        llm=llm,
        neo4j=neo4j,
        session=session,
    )

    if not result.ok:
        return {"error": result.error.model_dump()}

    entities, events, relations = result.entities, result.events, result.relations

    # 审计写入 Postgres
    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="kg.build",
            inputs={"assertion_uids": [a.uid for a in body.assertions]},
            outputs={
                "entity_count": len(entities),
                "event_count": len(events),
                "relation_count": len(relations),
            },
            trace_id=uuid4().hex,
        )
    )
    await session.commit()

    # Neo4j 已由 graphrag_pipeline 写入
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
    case_uid: str,
    version: str,
    from_version: str = "1.0.0",
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    report = await ontology_versioning.compute_compatibility_db(
        from_version, version, session
    )
    return {"result": report.model_dump()}


class DisambiguateRequest(BaseModel):
    entities: list[EntityV1]


@router.post("/cases/{case_uid}/kg/disambiguate")
async def disambiguate(
    case_uid: str,
    body: DisambiguateRequest,
    session: AsyncSession = Depends(get_db_session),
    llm: LLMClient = Depends(get_llm_client),
) -> dict:
    result = await disambiguate_entities(
        body.entities,
        case_uid=case_uid,
        llm=llm,
    )

    # 审计写入 Postgres
    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="kg.disambiguate",
            inputs=result.action.inputs,
            outputs=result.action.outputs,
            trace_id=result.action.trace_id,
        )
    )
    await session.commit()

    identity_action_uids: list[str] = []
    # merge 先写入身份 Action；真正执行由审批端点触发。
    for group in result.merge_groups:
        if group.uncertain:
            continue
        identity_action = await record_merge_identity_action(
            session,
            case_uid=case_uid,
            merge_group=group,
            reason=f"disambiguation merge confidence={group.confidence}",
            performed_by="llm",
            approved=False,
            created_by_action_uid=action_uid,
        )
        identity_action_uids.append(identity_action.uid)

    return {
        "merge_groups": [g.model_dump() for g in result.merge_groups],
        "unmatched_uids": result.unmatched_uids,
        "action_uid": action_uid,
        "identity_action_uids": identity_action_uids,
    }
