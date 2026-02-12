# Author: msq
from __future__ import annotations

from time import monotonic
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.errors import AegiHTTPError, not_found
from aegi_core.db.models.action import Action
from aegi_core.db.models.case import Case
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.tool_trace import ToolTrace
from aegi_core.services.tool_client import ToolClient


def _build_anchor_set(metadata: dict) -> list[dict]:
    """从 unstructured metadata 映射 anchor_set。"""
    anchors: list[dict] = []
    if page := metadata.get("page_number"):
        anchors.append({"type": "page", "value": page})
    if coords := metadata.get("coordinates"):
        anchors.append({"type": "coordinates", "value": coords})
    if filename := metadata.get("filename"):
        anchors.append({"type": "filename", "value": filename})
    if languages := metadata.get("languages"):
        anchors.append({"type": "languages", "value": languages})
    return anchors


async def call_tool_doc_parse(
    session: AsyncSession,
    tool: ToolClient,
    *,
    case_uid: str,
    artifact_version_uid: str,
    file_url: str,
    actor_id: str | None,
    rationale: str | None,
    inputs: dict,
) -> dict:
    """创建 Action，调用 ToolClient.doc_parse，记录 ToolTrace。"""
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)

    action_uid = f"act_{uuid4().hex}"
    action = Action(
        uid=action_uid,
        case_uid=case_uid,
        action_type="tool.doc_parse",
        actor_id=actor_id,
        rationale=rationale,
        inputs=inputs,
        outputs={},
    )
    session.add(action)
    await session.flush()

    start = monotonic()
    tool_trace_uid = f"tt_{uuid4().hex}"

    try:
        resp = await tool.doc_parse(
            artifact_version_uid=artifact_version_uid, file_url=file_url
        )
        duration_ms = int((monotonic() - start) * 1000)

        raw_chunks = resp.get("chunks", [])

        trace = ToolTrace(
            uid=tool_trace_uid,
            case_uid=case_uid,
            action_uid=action_uid,
            tool_name="doc_parse",
            request={
                "artifact_version_uid": artifact_version_uid,
                "file_url": file_url,
            },
            response={"ok": True, "chunk_count": len(raw_chunks)},
            status="ok",
            duration_ms=duration_ms,
            error=None,
            policy={},
        )
        session.add(trace)

        # ── 入库 Chunk + Evidence ──────────────────────────────────
        chunk_uids: list[str] = []
        evidence_uids: list[str] = []
        for idx, raw in enumerate(raw_chunks):
            c_uid = f"chk_{uuid4().hex}"
            e_uid = f"ev_{uuid4().hex}"
            meta = raw.get("metadata", {})
            session.add(
                Chunk(
                    uid=c_uid,
                    artifact_version_uid=artifact_version_uid,
                    ordinal=idx,
                    text=raw.get("text", ""),
                    anchor_set=_build_anchor_set(meta),
                )
            )
            session.add(
                Evidence(
                    uid=e_uid,
                    case_uid=case_uid,
                    artifact_version_uid=artifact_version_uid,
                    chunk_uid=c_uid,
                    kind="document_chunk",
                )
            )
            chunk_uids.append(c_uid)
            evidence_uids.append(e_uid)

        action.outputs = {
            "tool_trace_uid": tool_trace_uid,
            "chunk_uids": chunk_uids,
            "evidence_uids": evidence_uids,
        }
        await session.commit()

        return {
            "action_uid": action_uid,
            "tool_trace_uid": tool_trace_uid,
            "chunk_uids": chunk_uids,
            "evidence_uids": evidence_uids,
            "response": resp,
        }
    except AegiHTTPError as exc:
        duration_ms = int((monotonic() - start) * 1000)

        trace = ToolTrace(
            uid=tool_trace_uid,
            case_uid=case_uid,
            action_uid=action_uid,
            tool_name="doc_parse",
            request={
                "artifact_version_uid": artifact_version_uid,
                "file_url": file_url,
            },
            response={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
            status="error",
            duration_ms=duration_ms,
            error=exc.error_code,
            policy={},
        )
        session.add(trace)

        action.outputs = {
            "tool_trace_uid": tool_trace_uid,
            "error_code": exc.error_code,
        }
        await session.commit()
        raise
