"""文档上传 + 解析 + 证据入库端点。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_llm_client, get_qdrant_store
from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.infra.llm_client import LLMClient
from aegi_core.infra.qdrant_store import QdrantStore
from aegi_core.services.document_parser import parse_document, chunk_text, detect_format

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/document")
async def ingest_document(
    file: UploadFile = File(...),
    case_id: str = Form(""),
    actor_id: str = Form("system"),
    db: AsyncSession = Depends(get_db_session),
    llm: LLMClient = Depends(get_llm_client),
    qdrant: QdrantStore = Depends(get_qdrant_store),
) -> dict:
    """上传文档，解析、分块、作为证据入库。

    支持 PDF、DOCX、HTML、Markdown 和纯文本。
    返回创建的 artifact 和 evidence 元数据。
    """
    data = await file.read()
    filename = file.filename or "unknown"
    content_type = file.content_type or ""
    fmt = detect_format(filename, content_type)

    # 解析
    text = parse_document(data, filename=filename, content_type=content_type)
    if not text:
        return {"ok": False, "error": "No text extracted from document"}

    # 分块
    chunks_text = chunk_text(text)

    # 创建 artifact 链
    now = datetime.now(timezone.utc)
    if not case_id:
        return {"ok": False, "error": "case_id is required"}

    art_id = ArtifactIdentity(
        uid=uuid.uuid4().hex,
        kind=fmt,
        canonical_url=f"upload://{filename}",
        created_at=now,
    )
    art_ver = ArtifactVersion(
        uid=uuid.uuid4().hex,
        artifact_identity_uid=art_id.uid,
        case_uid=case_id,
        storage_ref=f"upload://{filename}",
        content_type=content_type or "application/octet-stream",
        created_at=now,
    )
    db.add(art_id)
    db.add(art_ver)

    evidence_uids = []
    for i, chunk_text_item in enumerate(chunks_text):
        chunk = Chunk(
            uid=uuid.uuid4().hex,
            artifact_version_uid=art_ver.uid,
            ordinal=i,
            text=chunk_text_item,
            created_at=now,
        )
        ev = Evidence(
            uid=uuid.uuid4().hex,
            case_uid=case_id,
            chunk_uid=chunk.uid,
            artifact_version_uid=art_ver.uid,
            kind=fmt,
            created_at=now,
        )
        db.add(chunk)
        db.add(ev)
        evidence_uids.append(ev.uid)

        # 向量化 + 索引
        from aegi_core.services.ingest_helpers import embed_and_index_chunk

        await embed_and_index_chunk(
            chunk_uid=chunk.uid,
            text=chunk_text_item,
            llm=llm,
            qdrant=qdrant,
            metadata={"case_uid": case_id, "filename": filename, "ordinal": i},
        )

    await db.commit()

    logger.info(
        "Ingested document %s: %d chunks, format=%s", filename, len(chunks_text), fmt
    )
    return {
        "ok": True,
        "filename": filename,
        "format": fmt,
        "text_length": len(text),
        "chunk_count": len(chunks_text),
        "artifact_uid": art_id.uid,
        "artifact_version_uid": art_ver.uid,
        "evidence_uids": evidence_uids,
    }


@router.post("/parse")
async def parse_only(
    file: UploadFile = File(...),
) -> dict:
    """只解析文档返回文本，不入库。

    用于入库前预览。
    """
    data = await file.read()
    filename = file.filename or "unknown"
    fmt = detect_format(filename, file.content_type or "")
    text = parse_document(data, filename=filename, content_type=file.content_type or "")
    return {
        "filename": filename,
        "format": fmt,
        "text_length": len(text),
        "text": text[:5000],  # 预览限制
        "truncated": len(text) > 5000,
    }
