"""证据链 Repository。

负责证据链（Artifact、Chunk、Evidence、Claim、Report）的数据库操作。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from baize_core.retention.policy import resolve_retention_policy
from baize_core.schemas.evidence import (
    AnchorType,
    Artifact,
    Chunk,
    ChunkAnchor,
    Claim,
    Evidence,
    EvidenceScore,
    Report,
    ReportReference,
)
from baize_core.storage import models


@dataclass
class EvidenceRepository:
    """证据链 Repository。

    Attributes:
        session_factory: SQLAlchemy 异步会话工厂
    """

    session_factory: async_sessionmaker[AsyncSession]

    # =========================================================================
    # 基础查询
    # =========================================================================

    async def get_artifacts_since(self, cutoff: datetime) -> list[models.ArtifactModel]:
        """获取指定时间之后的 Artifact。

        Args:
            cutoff: 截止时间

        Returns:
            Artifact 列表
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.ArtifactModel).where(
                    models.ArtifactModel.fetched_at >= cutoff
                )
            )
            return list(result.scalars().all())

    async def get_evidence_since(self, cutoff: datetime) -> list[models.EvidenceModel]:
        """获取指定时间之后的 Evidence。

        Args:
            cutoff: 截止时间

        Returns:
            Evidence 列表
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.EvidenceModel).where(
                    models.EvidenceModel.collected_at >= cutoff
                )
            )
            return list(result.scalars().all())

    async def get_artifact(self, artifact_uid: str) -> models.ArtifactModel | None:
        """获取指定 Artifact。

        Args:
            artifact_uid: Artifact UID

        Returns:
            Artifact，不存在时返回 None
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.ArtifactModel).where(
                    models.ArtifactModel.artifact_uid == artifact_uid
                )
            )
            return result.scalar_one_or_none()

    async def get_evidence(self, evidence_uid: str) -> models.EvidenceModel | None:
        """获取指定 Evidence。

        Args:
            evidence_uid: Evidence UID

        Returns:
            Evidence，不存在时返回 None
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.EvidenceModel).where(
                    models.EvidenceModel.evidence_uid == evidence_uid
                )
            )
            return result.scalar_one_or_none()

    # =========================================================================
    # 证据链读取
    # =========================================================================

    async def get_task_evidence_chain(self, task_id: str) -> dict[str, Any] | None:
        """获取任务证据链。

        Args:
            task_id: 任务 ID

        Returns:
            包含 claims, evidence, chunks, artifacts, report 的字典
        """
        async with self.session_factory() as session:
            report_result = await session.execute(
                select(models.ReportModel)
                .where(models.ReportModel.task_id == task_id)
                .order_by(models.ReportModel.created_at.desc())
                .limit(1)
            )
            report_row = report_result.scalar_one_or_none()
            if report_row is None:
                return None

            ref_result = await session.execute(
                select(models.ReportReferenceModel).where(
                    models.ReportReferenceModel.report_uid == report_row.report_uid
                )
            )
            refs = list(ref_result.scalars().all())
            references = [
                ReportReference(
                    citation=ref.citation,
                    evidence_uid=ref.evidence_uid,
                    chunk_uid=ref.chunk_uid,
                    artifact_uid=ref.artifact_uid,
                    source_url=ref.source_url,
                    anchor=ChunkAnchor(
                        type=AnchorType(ref.anchor_type),
                        ref=ref.anchor_ref,
                    ),
                )
                for ref in refs
            ]
            report = Report(
                report_uid=report_row.report_uid,
                task_id=report_row.task_id,
                outline_uid=report_row.outline_uid,
                report_type=report_row.report_type,
                content_ref=report_row.content_ref,
                references=references,
                conflict_notes=report_row.conflict_notes,
            )

            evidence_uids = {ref.evidence_uid for ref in refs if ref.evidence_uid}
            chunk_uids = {ref.chunk_uid for ref in refs if ref.chunk_uid}
            artifact_uids = {ref.artifact_uid for ref in refs if ref.artifact_uid}

            evidence_rows: list[models.EvidenceModel] = []
            if evidence_uids:
                evidence_result = await session.execute(
                    select(models.EvidenceModel).where(
                        models.EvidenceModel.evidence_uid.in_(evidence_uids)
                    )
                )
                evidence_rows = list(evidence_result.scalars().all())

            chunk_rows: list[models.ChunkModel] = []
            if chunk_uids:
                chunk_result = await session.execute(
                    select(models.ChunkModel).where(
                        models.ChunkModel.chunk_uid.in_(chunk_uids)
                    )
                )
                chunk_rows = list(chunk_result.scalars().all())

            artifact_rows: list[models.ArtifactModel] = []
            if artifact_uids:
                artifact_result = await session.execute(
                    select(models.ArtifactModel).where(
                        models.ArtifactModel.artifact_uid.in_(artifact_uids)
                    )
                )
                artifact_rows = list(artifact_result.scalars().all())

            evidence_items = [
                Evidence(
                    evidence_uid=row.evidence_uid,
                    chunk_uid=row.chunk_uid,
                    source=row.source,
                    uri=row.uri,
                    collected_at=row.collected_at,
                    base_credibility=row.base_credibility,
                    score=EvidenceScore.model_validate(row.score)
                    if row.score is not None
                    else None,
                    conflict_types=row.conflict_types,
                    conflict_with=row.conflict_with,
                    tags=row.tags,
                    summary=row.summary,
                )
                for row in evidence_rows
            ]
            chunks = [
                Chunk(
                    chunk_uid=row.chunk_uid,
                    artifact_uid=row.artifact_uid,
                    anchor=ChunkAnchor(
                        type=AnchorType(row.anchor_type),
                        ref=row.anchor_ref,
                    ),
                    text=row.text,
                    text_sha256=row.text_sha256,
                )
                for row in chunk_rows
            ]
            artifacts = [
                Artifact(
                    artifact_uid=row.artifact_uid,
                    source_url=row.source_url,
                    fetched_at=row.fetched_at,
                    content_sha256=row.content_sha256,
                    mime_type=row.mime_type,
                    storage_ref=row.storage_ref,
                    origin_tool=row.origin_tool,
                    fetch_trace_id=row.fetch_trace_id,
                    license_note=row.license_note,
                )
                for row in artifact_rows
            ]

            claim_result = []
            if evidence_uids:
                claim_rows = (
                    await session.execute(
                        select(models.ClaimModel)
                        .join(
                            models.ClaimEvidenceModel,
                            models.ClaimEvidenceModel.claim_uid
                            == models.ClaimModel.claim_uid,
                        )
                        .where(
                            models.ClaimEvidenceModel.evidence_uid.in_(evidence_uids)
                        )
                    )
                ).scalars()
                claim_rows = list(claim_rows)
                claim_links = (
                    await session.execute(
                        select(
                            models.ClaimEvidenceModel.claim_uid,
                            models.ClaimEvidenceModel.evidence_uid,
                        ).where(
                            models.ClaimEvidenceModel.evidence_uid.in_(evidence_uids)
                        )
                    )
                ).all()
                claim_map: dict[str, list[str]] = {}
                for claim_uid, evidence_uid in claim_links:
                    claim_map.setdefault(claim_uid, []).append(evidence_uid)
                claim_result = [
                    Claim(
                        claim_uid=row.claim_uid,
                        statement=row.statement,
                        confidence=row.confidence,
                        contradictions=row.contradictions,
                        evidence_uids=claim_map.get(row.claim_uid, []),
                    )
                    for row in claim_rows
                ]

            return {
                "claims": claim_result,
                "evidence": evidence_items,
                "chunks": chunks,
                "artifacts": artifacts,
                "report": report,
            }

    # =========================================================================
    # 写入操作
    # =========================================================================

    async def store_artifacts(self, artifacts: list[Artifact]) -> None:
        """写入 Artifact。

        Args:
            artifacts: Artifact 列表
        """
        if not artifacts:
            return
        policy = resolve_retention_policy()
        async with self.session_factory() as session:
            payload = [
                {
                    "artifact_uid": artifact.artifact_uid,
                    "source_url": artifact.source_url,
                    "fetched_at": artifact.fetched_at,
                    "expires_at": artifact.fetched_at
                    + timedelta(days=policy.artifact_retention_days),
                    "content_sha256": artifact.content_sha256,
                    "mime_type": artifact.mime_type,
                    "storage_ref": artifact.storage_ref,
                    "origin_tool": artifact.origin_tool,
                    "fetch_trace_id": artifact.fetch_trace_id,
                    "license_note": artifact.license_note,
                }
                for artifact in artifacts
            ]
            stmt = insert(models.ArtifactModel).values(payload)
            stmt = stmt.on_conflict_do_nothing(index_elements=["artifact_uid"])
            await session.execute(stmt)
            await session.commit()

    async def store_evidence_chain(
        self,
        *,
        artifacts: list[Artifact],
        chunks: list[Chunk],
        evidence_items: list[Evidence],
        claims: list[Claim],
    ) -> None:
        """写入完整证据链。

        Args:
            artifacts: Artifact 列表
            chunks: Chunk 列表
            evidence_items: Evidence 列表
            claims: Claim 列表
        """
        policy = resolve_retention_policy()
        now = datetime.now(UTC)
        artifact_fetched_at: dict[str, datetime] = {
            artifact.artifact_uid: artifact.fetched_at for artifact in artifacts
        }
        async with self.session_factory() as session:
            if artifacts:
                artifact_payload = [
                    {
                        "artifact_uid": artifact.artifact_uid,
                        "source_url": artifact.source_url,
                        "fetched_at": artifact.fetched_at,
                        "expires_at": artifact.fetched_at
                        + timedelta(days=policy.artifact_retention_days),
                        "content_sha256": artifact.content_sha256,
                        "mime_type": artifact.mime_type,
                        "storage_ref": artifact.storage_ref,
                        "origin_tool": artifact.origin_tool,
                        "fetch_trace_id": artifact.fetch_trace_id,
                        "license_note": artifact.license_note,
                    }
                    for artifact in artifacts
                ]
                stmt = insert(models.ArtifactModel).values(artifact_payload)
                stmt = stmt.on_conflict_do_nothing(index_elements=["artifact_uid"])
                await session.execute(stmt)
            if chunks:
                # 每个 chunk 有 7 个参数，PostgreSQL 最多支持 32767 个参数
                # 为安全起见，每批最多 4000 个 chunks
                batch_size = 4000
                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i : i + batch_size]
                    chunk_payload = [
                        {
                            "chunk_uid": chunk.chunk_uid,
                            "artifact_uid": chunk.artifact_uid,
                            "expires_at": artifact_fetched_at.get(chunk.artifact_uid, now)
                            + timedelta(days=policy.chunk_retention_days),
                            "anchor_type": chunk.anchor.type.value,
                            "anchor_ref": chunk.anchor.ref,
                            "text": chunk.text,
                            "text_sha256": chunk.text_sha256,
                        }
                        for chunk in batch
                    ]
                    stmt = insert(models.ChunkModel).values(chunk_payload)
                    stmt = stmt.on_conflict_do_nothing(index_elements=["chunk_uid"])
                    await session.execute(stmt)
            if evidence_items:
                # 每个 evidence 有 12 个参数，PostgreSQL 最多支持 32767 个参数
                # 为安全起见，每批最多 2500 个 evidence
                batch_size = 2500
                for i in range(0, len(evidence_items), batch_size):
                    batch = evidence_items[i : i + batch_size]
                    evidence_payload: list[dict[str, Any]] = [
                        {
                            "evidence_uid": evidence_item.evidence_uid,
                            "chunk_uid": evidence_item.chunk_uid,
                            "expires_at": evidence_item.collected_at
                            + timedelta(days=policy.evidence_retention_days),
                            "source": evidence_item.source,
                            "uri": evidence_item.uri,
                            "collected_at": evidence_item.collected_at,
                            "base_credibility": evidence_item.base_credibility,
                            "score": evidence_item.score.model_dump()
                            if evidence_item.score is not None
                            else None,
                            "conflict_types": evidence_item.conflict_types,
                            "conflict_with": evidence_item.conflict_with,
                            "tags": evidence_item.tags,
                            "summary": evidence_item.summary,
                        }
                        for evidence_item in batch
                    ]
                    stmt = insert(models.EvidenceModel).values(evidence_payload)
                    stmt = stmt.on_conflict_do_nothing(index_elements=["evidence_uid"])
                    await session.execute(stmt)
            if claims:
                claims_payload: list[dict[str, Any]] = [
                    {
                        "claim_uid": claim.claim_uid,
                        "statement": claim.statement,
                        "confidence": claim.confidence,
                        "contradictions": claim.contradictions,
                    }
                    for claim in claims
                ]
                stmt = insert(models.ClaimModel).values(claims_payload)
                stmt = stmt.on_conflict_do_nothing(index_elements=["claim_uid"])
                await session.execute(stmt)
            if claims:
                claim_evidence_payload = [
                    {
                        "claim_uid": claim.claim_uid,
                        "evidence_uid": evidence_uid,
                    }
                    for claim in claims
                    for evidence_uid in claim.evidence_uids
                ]
                if claim_evidence_payload:
                    stmt = insert(models.ClaimEvidenceModel).values(
                        claim_evidence_payload
                    )
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["claim_uid", "evidence_uid"]
                    )
                    await session.execute(stmt)
            await session.commit()

    async def store_chunks(self, chunks: list[Chunk]) -> None:
        """写入 Chunk。

        Args:
            chunks: Chunk 列表
        """
        if not chunks:
            return
        policy = resolve_retention_policy()
        now = datetime.now(UTC)
        # 每个 chunk 有 7 个参数，PostgreSQL 最多支持 32767 个参数
        # 为安全起见，每批最多 4000 个 chunks
        batch_size = 4000
        async with self.session_factory() as session:
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                payload = [
                    {
                        "chunk_uid": chunk.chunk_uid,
                        "artifact_uid": chunk.artifact_uid,
                        "expires_at": now + timedelta(days=policy.chunk_retention_days),
                        "anchor_type": chunk.anchor.type.value,
                        "anchor_ref": chunk.anchor.ref,
                        "text": chunk.text,
                        "text_sha256": chunk.text_sha256,
                    }
                    for chunk in batch
                ]
                stmt = insert(models.ChunkModel).values(payload)
                stmt = stmt.on_conflict_do_nothing(index_elements=["chunk_uid"])
                await session.execute(stmt)
            await session.commit()

    async def store_evidence(self, evidence_items: list[Evidence]) -> None:
        """写入 Evidence。

        Args:
            evidence_items: Evidence 列表
        """
        if not evidence_items:
            return
        policy = resolve_retention_policy()
        # 每个 evidence 有 12 个参数，PostgreSQL 最多支持 32767 个参数
        # 为安全起见，每批最多 2500 个 evidence
        batch_size = 2500
        async with self.session_factory() as session:
            for i in range(0, len(evidence_items), batch_size):
                batch = evidence_items[i : i + batch_size]
                payload = [
                    {
                        "evidence_uid": evidence_item.evidence_uid,
                        "chunk_uid": evidence_item.chunk_uid,
                        "expires_at": evidence_item.collected_at
                        + timedelta(days=policy.evidence_retention_days),
                        "source": evidence_item.source,
                        "uri": evidence_item.uri,
                        "collected_at": evidence_item.collected_at,
                        "base_credibility": evidence_item.base_credibility,
                        "score": evidence_item.score.model_dump()
                        if evidence_item.score is not None
                        else None,
                        "conflict_types": evidence_item.conflict_types,
                        "conflict_with": evidence_item.conflict_with,
                        "tags": evidence_item.tags,
                        "summary": evidence_item.summary,
                    }
                    for evidence_item in batch
                ]
                stmt = insert(models.EvidenceModel).values(payload)
                stmt = stmt.on_conflict_do_nothing(index_elements=["evidence_uid"])
                await session.execute(stmt)
            await session.commit()

    async def store_claims(self, claims: list[Claim]) -> None:
        """写入 Claim 与关联表。

        Args:
            claims: Claim 列表
        """
        if not claims:
            return
        async with self.session_factory() as session:
            payload = [
                {
                    "claim_uid": claim.claim_uid,
                    "statement": claim.statement,
                    "confidence": claim.confidence,
                    "contradictions": claim.contradictions,
                }
                for claim in claims
            ]
            stmt = insert(models.ClaimModel).values(payload)
            stmt = stmt.on_conflict_do_nothing(index_elements=["claim_uid"])
            await session.execute(stmt)
            await session.commit()

        async with self.session_factory() as session:
            payload = [
                {
                    "claim_uid": claim.claim_uid,
                    "evidence_uid": evidence_uid,
                }
                for claim in claims
                for evidence_uid in claim.evidence_uids
            ]
            if payload:
                stmt = insert(models.ClaimEvidenceModel).values(payload)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["claim_uid", "evidence_uid"]
                )
                await session.execute(stmt)
                await session.commit()

    async def store_report(self, report: Report) -> None:
        """写入 Report 与引用。

        Args:
            report: Report 对象
        """
        async with self.session_factory() as session:
            session.add(
                models.ReportModel(
                    report_uid=report.report_uid,
                    task_id=report.task_id,
                    outline_uid=report.outline_uid,
                    report_type=report.report_type,
                    content_ref=report.content_ref,
                    conflict_notes=report.conflict_notes,
                    created_at=datetime.now(UTC),
                )
            )
            for reference in report.references:
                session.add(
                    models.ReportReferenceModel(
                        report_uid=report.report_uid,
                        citation=reference.citation,
                        evidence_uid=reference.evidence_uid,
                        chunk_uid=reference.chunk_uid,
                        artifact_uid=reference.artifact_uid,
                        source_url=reference.source_url,
                        anchor_type=reference.anchor.type.value,
                        anchor_ref=reference.anchor.ref,
                    )
                )
            # 维护 artifacts.reference_count（按 report_references 重算）
            artifact_uids = {ref.artifact_uid for ref in report.references}
            if artifact_uids:
                await session.flush()
                ref_rows = (
                    await session.execute(
                        select(
                            models.ReportReferenceModel.artifact_uid,
                            func.count(models.ReportReferenceModel.artifact_uid),
                        )
                        .where(
                            models.ReportReferenceModel.artifact_uid.in_(
                                list(artifact_uids)
                            )
                        )
                        .group_by(models.ReportReferenceModel.artifact_uid)
                    )
                ).all()
                ref_map = {uid: int(cnt) for uid, cnt in ref_rows}
                ref_case = case(
                    *(
                        (
                            models.ArtifactModel.artifact_uid == uid,
                            ref_map.get(uid, 0),
                        )
                        for uid in artifact_uids
                    ),
                    else_=0,
                )
                await session.execute(
                    sqlalchemy.update(models.ArtifactModel)
                    .where(models.ArtifactModel.artifact_uid.in_(list(artifact_uids)))
                    .values(reference_count=ref_case)
                )
            await session.commit()

    # =========================================================================
    # 辅助方法
    # =========================================================================

    async def create_artifact(
        self,
        *,
        artifact_uid: str,
        storage_ref: str,
        source_url: str,
        fetched_at: datetime,
        content_sha256: str,
        mime_type: str,
        origin_tool: str | None = None,
        fetch_trace_id: str | None = None,
        license_note: str | None = None,
    ) -> models.ArtifactModel:
        """创建单个 Artifact 记录。

        Args:
            artifact_uid: Artifact UID
            storage_ref: 存储引用
            source_url: 来源 URL
            fetched_at: 抓取时间
            content_sha256: 内容哈希
            mime_type: MIME 类型
            origin_tool: 来源工具
            fetch_trace_id: 抓取追踪 ID
            license_note: 许可说明

        Returns:
            创建的 Artifact 记录
        """
        policy = resolve_retention_policy()
        async with self.session_factory() as session:
            record = models.ArtifactModel(
                artifact_uid=artifact_uid,
                storage_ref=storage_ref,
                source_url=source_url,
                fetched_at=fetched_at,
                expires_at=fetched_at + timedelta(days=policy.artifact_retention_days),
                content_sha256=content_sha256,
                mime_type=mime_type,
                origin_tool=origin_tool,
                fetch_trace_id=fetch_trace_id,
                license_note=license_note,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def save_quality_report(self, report: dict[str, Any]) -> None:
        """保存质量报告（预留接口）。"""
        return None

    async def get_unindexed_chunks(self, limit: int) -> list[dict[str, Any]]:
        """获取待索引的 Chunk 列表。

        Args:
            limit: 返回数量限制

        Returns:
            Chunk 字典列表
        """
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(models.ChunkModel)
                    .where(models.ChunkModel.deleted_at.is_(None))
                    .limit(limit)
                )
            ).scalars()
            return [
                {
                    "chunk_uid": row.chunk_uid,
                    "artifact_uid": row.artifact_uid,
                    "text": row.text,
                    "anchor": {"type": row.anchor_type, "ref": row.anchor_ref},
                }
                for row in rows
            ]

    async def mark_chunk_indexed(self, chunk_uid: str) -> None:
        """标记 Chunk 已索引（当前为兼容占位）。"""
        return None
