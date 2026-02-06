"""数据保留 Repository。

负责数据保留策略（软删除、过期标记、物理删除）的数据库操作。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from baize_core.storage import models


def _rowcount(result: Any) -> int:
    """获取 rowcount 统计。"""
    return int(getattr(result, "rowcount", 0) or 0)


@dataclass
class RetentionRepository:
    """数据保留 Repository。

    Attributes:
        session_factory: SQLAlchemy 异步会话工厂
    """

    session_factory: async_sessionmaker[AsyncSession]

    async def soft_delete_task_data(self, task_id: str) -> dict[str, int]:
        """按 task_id 软删除关联证据链数据（artifact/chunk/evidence）。

        说明：
        - 软删除通过设置 deleted_at / expires_at 实现
        - 为避免误删共享数据：仅删除"在移除本任务引用后不再被任何引用"的记录

        Args:
            task_id: 任务 ID

        Returns:
            删除统计
        """
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            # 1) 收集候选（来自 report_references + storm_section_evidence）
            report_refs_stmt = (
                select(
                    models.ReportReferenceModel.evidence_uid,
                    models.ReportReferenceModel.chunk_uid,
                    models.ReportReferenceModel.artifact_uid,
                )
                .join(
                    models.ReportModel,
                    models.ReportModel.report_uid
                    == models.ReportReferenceModel.report_uid,
                )
                .where(models.ReportModel.task_id == task_id)
            )
            report_rows = (await session.execute(report_refs_stmt)).all()

            # storm: evidence_uid -> chunk_uid -> artifact_uid
            storm_refs_stmt = (
                select(
                    models.StormSectionEvidenceModel.evidence_uid,
                    models.EvidenceModel.chunk_uid,
                    models.ChunkModel.artifact_uid,
                )
                .join(
                    models.StormSectionModel,
                    models.StormSectionModel.section_uid
                    == models.StormSectionEvidenceModel.section_uid,
                )
                .join(
                    models.StormOutlineModel,
                    models.StormOutlineModel.outline_uid
                    == models.StormSectionModel.outline_uid,
                )
                .join(
                    models.EvidenceModel,
                    models.EvidenceModel.evidence_uid
                    == models.StormSectionEvidenceModel.evidence_uid,
                )
                .join(
                    models.ChunkModel,
                    models.ChunkModel.chunk_uid == models.EvidenceModel.chunk_uid,
                )
                .where(models.StormOutlineModel.task_id == task_id)
            )
            storm_rows = (await session.execute(storm_refs_stmt)).all()

            candidate_evidence = {row[0] for row in report_rows} | {
                row[0] for row in storm_rows
            }
            candidate_chunks = {row[1] for row in report_rows} | {
                row[1] for row in storm_rows
            }
            candidate_artifacts = {row[2] for row in report_rows} | {
                row[2] for row in storm_rows
            }

            # 2) 移除"本任务"的引用关系（report + storm）
            report_uids_stmt = select(models.ReportModel.report_uid).where(
                models.ReportModel.task_id == task_id
            )
            await session.execute(
                sqlalchemy.delete(models.ReportReferenceModel).where(
                    models.ReportReferenceModel.report_uid.in_(report_uids_stmt)
                )
            )
            await session.execute(
                sqlalchemy.delete(models.ReportModel).where(
                    models.ReportModel.task_id == task_id
                )
            )

            outline_uids_stmt = select(models.StormOutlineModel.outline_uid).where(
                models.StormOutlineModel.task_id == task_id
            )
            section_uids_stmt = select(models.StormSectionModel.section_uid).where(
                models.StormSectionModel.outline_uid.in_(outline_uids_stmt)
            )
            await session.execute(
                sqlalchemy.delete(models.StormSectionEvidenceModel).where(
                    models.StormSectionEvidenceModel.section_uid.in_(section_uids_stmt)
                )
            )
            await session.execute(
                sqlalchemy.delete(models.StormSectionIterationModel).where(
                    models.StormSectionIterationModel.section_uid.in_(section_uids_stmt)
                )
            )
            await session.execute(
                sqlalchemy.delete(models.StormSectionModel).where(
                    models.StormSectionModel.outline_uid.in_(outline_uids_stmt)
                )
            )
            await session.execute(
                sqlalchemy.delete(models.StormOutlineModel).where(
                    models.StormOutlineModel.task_id == task_id
                )
            )

            # 3) 计算移除引用后，仍被引用的数据（避免误删共享数据）
            referenced_evidence: set[str] = set()
            referenced_chunks: set[str] = set()
            referenced_artifacts: set[str] = set()

            if candidate_evidence:
                referenced_evidence |= set(
                    (
                        await session.execute(
                            select(models.ReportReferenceModel.evidence_uid).where(
                                models.ReportReferenceModel.evidence_uid.in_(
                                    list(candidate_evidence)
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                referenced_evidence |= set(
                    (
                        await session.execute(
                            select(models.StormSectionEvidenceModel.evidence_uid).where(
                                models.StormSectionEvidenceModel.evidence_uid.in_(
                                    list(candidate_evidence)
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            if candidate_chunks:
                referenced_chunks |= set(
                    (
                        await session.execute(
                            select(models.ReportReferenceModel.chunk_uid).where(
                                models.ReportReferenceModel.chunk_uid.in_(
                                    list(candidate_chunks)
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                # 通过"仍被引用的 evidence" 反推 chunk
                if referenced_evidence:
                    referenced_chunks |= set(
                        (
                            await session.execute(
                                select(models.EvidenceModel.chunk_uid).where(
                                    models.EvidenceModel.evidence_uid.in_(
                                        list(referenced_evidence)
                                    )
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
            if candidate_artifacts:
                referenced_artifacts |= set(
                    (
                        await session.execute(
                            select(models.ReportReferenceModel.artifact_uid).where(
                                models.ReportReferenceModel.artifact_uid.in_(
                                    list(candidate_artifacts)
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if referenced_chunks:
                    referenced_artifacts |= set(
                        (
                            await session.execute(
                                select(models.ChunkModel.artifact_uid).where(
                                    models.ChunkModel.chunk_uid.in_(
                                        list(referenced_chunks)
                                    )
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )

            delete_evidence = candidate_evidence - referenced_evidence
            delete_chunks = candidate_chunks - referenced_chunks
            delete_artifacts = candidate_artifacts - referenced_artifacts

            # 4) 更新 artifact.reference_count（按 report_references 重算）
            updated_refcount = 0
            if candidate_artifacts:
                ref_rows = (
                    await session.execute(
                        select(
                            models.ReportReferenceModel.artifact_uid,
                            func.count(models.ReportReferenceModel.artifact_uid),
                        )
                        .where(
                            models.ReportReferenceModel.artifact_uid.in_(
                                list(candidate_artifacts)
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
                        for uid in candidate_artifacts
                    ),
                    else_=0,
                )
                stmt = (
                    sqlalchemy.update(models.ArtifactModel)
                    .where(
                        models.ArtifactModel.artifact_uid.in_(list(candidate_artifacts))
                    )
                    .values(reference_count=ref_case)
                )
                result = await session.execute(stmt)
                updated_refcount = _rowcount(result)

            # 5) 软删除（deleted_at + expires_at）
            deleted_evidence = 0
            deleted_chunks = 0
            deleted_artifacts_count = 0

            if delete_evidence:
                result = await session.execute(
                    sqlalchemy.update(models.EvidenceModel)
                    .where(models.EvidenceModel.evidence_uid.in_(list(delete_evidence)))
                    .values(deleted_at=now, expires_at=now)
                )
                deleted_evidence = _rowcount(result)
            if delete_chunks:
                result = await session.execute(
                    sqlalchemy.update(models.ChunkModel)
                    .where(models.ChunkModel.chunk_uid.in_(list(delete_chunks)))
                    .values(deleted_at=now, expires_at=now)
                )
                deleted_chunks = _rowcount(result)
            if delete_artifacts:
                # 仅在 reference_count==0 时标记删除（避免误删共享 Artifact）
                result = await session.execute(
                    sqlalchemy.update(models.ArtifactModel)
                    .where(
                        models.ArtifactModel.artifact_uid.in_(list(delete_artifacts)),
                        models.ArtifactModel.reference_count == 0,
                    )
                    .values(deleted_at=now, expires_at=now)
                )
                deleted_artifacts_count = _rowcount(result)

            await session.commit()
            return {
                "candidates": len(candidate_evidence)
                + len(candidate_chunks)
                + len(candidate_artifacts),
                "deleted_evidence": deleted_evidence,
                "deleted_chunks": deleted_chunks,
                "deleted_artifacts": deleted_artifacts_count,
                "updated_artifact_refcount": updated_refcount,
            }

    async def mark_expired_unreferenced(
        self, *, now: datetime | None = None, batch_size: int = 200
    ) -> dict[str, int]:
        """标记过期且无引用的数据为软删除（deleted_at）。

        Args:
            now: 当前时间（默认为 UTC 时间）
            batch_size: 批处理大小

        Returns:
            标记统计
        """
        ts = now or datetime.now(UTC)
        async with self.session_factory() as session:
            # Evidence：未删除、已过期、且不在 report_references / storm_section_evidence 中
            rr_exists = (
                select(models.ReportReferenceModel.evidence_uid)
                .where(
                    models.ReportReferenceModel.evidence_uid
                    == models.EvidenceModel.evidence_uid
                )
                .exists()
            )
            storm_exists = (
                select(models.StormSectionEvidenceModel.evidence_uid)
                .where(
                    models.StormSectionEvidenceModel.evidence_uid
                    == models.EvidenceModel.evidence_uid
                )
                .exists()
            )
            evidence_uids = (
                (
                    await session.execute(
                        select(models.EvidenceModel.evidence_uid)
                        .where(
                            models.EvidenceModel.deleted_at.is_(None),
                            models.EvidenceModel.expires_at.is_not(None),
                            models.EvidenceModel.expires_at <= ts,
                            ~rr_exists,
                            ~storm_exists,
                        )
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            marked_evidence = 0
            if evidence_uids:
                result = await session.execute(
                    sqlalchemy.update(models.EvidenceModel)
                    .where(models.EvidenceModel.evidence_uid.in_(evidence_uids))
                    .values(deleted_at=ts)
                )
                marked_evidence = _rowcount(result)

            # Chunk：未删除、已过期、且无 report 引用、且不存在未删除 evidence
            chunk_rr_exists = (
                select(models.ReportReferenceModel.chunk_uid)
                .where(
                    models.ReportReferenceModel.chunk_uid == models.ChunkModel.chunk_uid
                )
                .exists()
            )
            active_evidence_exists = (
                select(models.EvidenceModel.chunk_uid)
                .where(
                    models.EvidenceModel.chunk_uid == models.ChunkModel.chunk_uid,
                    models.EvidenceModel.deleted_at.is_(None),
                )
                .exists()
            )
            chunk_uids = (
                (
                    await session.execute(
                        select(models.ChunkModel.chunk_uid)
                        .where(
                            models.ChunkModel.deleted_at.is_(None),
                            models.ChunkModel.expires_at.is_not(None),
                            models.ChunkModel.expires_at <= ts,
                            ~chunk_rr_exists,
                            ~active_evidence_exists,
                        )
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            marked_chunks = 0
            if chunk_uids:
                result = await session.execute(
                    sqlalchemy.update(models.ChunkModel)
                    .where(models.ChunkModel.chunk_uid.in_(chunk_uids))
                    .values(deleted_at=ts)
                )
                marked_chunks = _rowcount(result)

            # Artifact：未删除、已过期、且 reference_count==0、且不存在未删除 chunk
            active_chunk_exists = (
                select(models.ChunkModel.artifact_uid)
                .where(
                    models.ChunkModel.artifact_uid == models.ArtifactModel.artifact_uid,
                    models.ChunkModel.deleted_at.is_(None),
                )
                .exists()
            )
            artifact_uids = (
                (
                    await session.execute(
                        select(models.ArtifactModel.artifact_uid)
                        .where(
                            models.ArtifactModel.deleted_at.is_(None),
                            models.ArtifactModel.expires_at.is_not(None),
                            models.ArtifactModel.expires_at <= ts,
                            models.ArtifactModel.reference_count == 0,
                            ~active_chunk_exists,
                        )
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            marked_artifacts = 0
            if artifact_uids:
                result = await session.execute(
                    sqlalchemy.update(models.ArtifactModel)
                    .where(models.ArtifactModel.artifact_uid.in_(artifact_uids))
                    .values(deleted_at=ts)
                )
                marked_artifacts = _rowcount(result)

            await session.commit()
            return {
                "marked_evidence": marked_evidence,
                "marked_chunks": marked_chunks,
                "marked_artifacts": marked_artifacts,
            }

    async def hard_delete_soft_deleted_data(
        self,
        *,
        now: datetime | None = None,
        grace_days: int = 7,
        batch_size: int = 200,
    ) -> dict[str, object]:
        """物理删除已软删除且超过宽限期的数据（返回 MinIO storage_ref 列表）。

        Args:
            now: 当前时间（默认为 UTC 时间）
            grace_days: 宽限期天数
            batch_size: 批处理大小

        Returns:
            删除统计及需要清理的 storage_ref 列表
        """
        if grace_days <= 0:
            raise ValueError("grace_days 必须大于 0")
        ts = now or datetime.now(UTC)
        threshold = ts - timedelta(days=grace_days)

        async with self.session_factory() as session:
            # 1) Evidence：先删关联表，再删 evidence
            evidence_uids = (
                (
                    await session.execute(
                        select(models.EvidenceModel.evidence_uid)
                        .where(
                            models.EvidenceModel.deleted_at.is_not(None),
                            models.EvidenceModel.deleted_at <= threshold,
                        )
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            deleted_evidence = 0
            if evidence_uids:
                await session.execute(
                    sqlalchemy.delete(models.ClaimEvidenceModel).where(
                        models.ClaimEvidenceModel.evidence_uid.in_(evidence_uids)
                    )
                )
                await session.execute(
                    sqlalchemy.delete(models.EntityEvidenceModel).where(
                        models.EntityEvidenceModel.evidence_uid.in_(evidence_uids)
                    )
                )
                # 防御性清理：理论上软删除时已移除引用
                await session.execute(
                    sqlalchemy.delete(models.ReportReferenceModel).where(
                        models.ReportReferenceModel.evidence_uid.in_(evidence_uids)
                    )
                )
                await session.execute(
                    sqlalchemy.delete(models.StormSectionEvidenceModel).where(
                        models.StormSectionEvidenceModel.evidence_uid.in_(evidence_uids)
                    )
                )
                result = await session.execute(
                    sqlalchemy.delete(models.EvidenceModel).where(
                        models.EvidenceModel.evidence_uid.in_(evidence_uids)
                    )
                )
                deleted_evidence = _rowcount(result)

            # 2) Chunk：要求不存在 evidence
            evidence_exists = (
                select(models.EvidenceModel.chunk_uid)
                .where(models.EvidenceModel.chunk_uid == models.ChunkModel.chunk_uid)
                .exists()
            )
            chunk_uids = (
                (
                    await session.execute(
                        select(models.ChunkModel.chunk_uid)
                        .where(
                            models.ChunkModel.deleted_at.is_not(None),
                            models.ChunkModel.deleted_at <= threshold,
                            ~evidence_exists,
                        )
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            deleted_chunks = 0
            if chunk_uids:
                await session.execute(
                    sqlalchemy.delete(models.ReportReferenceModel).where(
                        models.ReportReferenceModel.chunk_uid.in_(chunk_uids)
                    )
                )
                result = await session.execute(
                    sqlalchemy.delete(models.ChunkModel).where(
                        models.ChunkModel.chunk_uid.in_(chunk_uids)
                    )
                )
                deleted_chunks = _rowcount(result)

            # 3) Artifact：要求不存在 chunk，且 reference_count==0
            chunk_exists = (
                select(models.ChunkModel.artifact_uid)
                .where(
                    models.ChunkModel.artifact_uid == models.ArtifactModel.artifact_uid
                )
                .exists()
            )
            artifact_rows = (
                await session.execute(
                    select(
                        models.ArtifactModel.artifact_uid,
                        models.ArtifactModel.storage_ref,
                    )
                    .where(
                        models.ArtifactModel.deleted_at.is_not(None),
                        models.ArtifactModel.deleted_at <= threshold,
                        models.ArtifactModel.reference_count == 0,
                        ~chunk_exists,
                    )
                    .limit(batch_size)
                )
            ).all()
            artifact_uids = [row[0] for row in artifact_rows]
            storage_refs = [row[1] for row in artifact_rows]
            deleted_artifacts = 0
            if artifact_uids:
                await session.execute(
                    sqlalchemy.delete(models.ReportReferenceModel).where(
                        models.ReportReferenceModel.artifact_uid.in_(artifact_uids)
                    )
                )
                result = await session.execute(
                    sqlalchemy.delete(models.ArtifactModel).where(
                        models.ArtifactModel.artifact_uid.in_(artifact_uids)
                    )
                )
                deleted_artifacts = _rowcount(result)

            await session.commit()
            return {
                "deleted_evidence": deleted_evidence,
                "deleted_chunks": deleted_chunks,
                "deleted_artifacts": deleted_artifacts,
                "storage_refs": storage_refs,
            }

    async def get_stats(self, *, grace_days: int = 7) -> dict[str, int]:
        """获取 retention/cleanup 统计信息。

        Args:
            grace_days: 宽限期天数

        Returns:
            统计信息字典
        """
        if grace_days <= 0:
            raise ValueError("grace_days 必须大于 0")
        ts = datetime.now(UTC)
        threshold = ts - timedelta(days=grace_days)

        async with self.session_factory() as session:
            # Evidence
            evidence_total = int(
                (
                    await session.execute(
                        select(func.count()).select_from(models.EvidenceModel)
                    )
                ).scalar_one()
            )
            evidence_soft_deleted = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(models.EvidenceModel)
                        .where(models.EvidenceModel.deleted_at.is_not(None))
                    )
                ).scalar_one()
            )
            evidence_expired = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(models.EvidenceModel)
                        .where(
                            models.EvidenceModel.expires_at.is_not(None),
                            models.EvidenceModel.expires_at <= ts,
                        )
                    )
                ).scalar_one()
            )
            evidence_hard_delete_ready = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(models.EvidenceModel)
                        .where(
                            models.EvidenceModel.deleted_at.is_not(None),
                            models.EvidenceModel.deleted_at <= threshold,
                        )
                    )
                ).scalar_one()
            )

            # Chunk
            chunks_total = int(
                (
                    await session.execute(
                        select(func.count()).select_from(models.ChunkModel)
                    )
                ).scalar_one()
            )
            chunks_soft_deleted = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(models.ChunkModel)
                        .where(models.ChunkModel.deleted_at.is_not(None))
                    )
                ).scalar_one()
            )
            chunks_expired = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(models.ChunkModel)
                        .where(
                            models.ChunkModel.expires_at.is_not(None),
                            models.ChunkModel.expires_at <= ts,
                        )
                    )
                ).scalar_one()
            )
            chunks_hard_delete_ready = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(models.ChunkModel)
                        .where(
                            models.ChunkModel.deleted_at.is_not(None),
                            models.ChunkModel.deleted_at <= threshold,
                        )
                    )
                ).scalar_one()
            )

            # Artifact
            artifacts_total = int(
                (
                    await session.execute(
                        select(func.count()).select_from(models.ArtifactModel)
                    )
                ).scalar_one()
            )
            artifacts_soft_deleted = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(models.ArtifactModel)
                        .where(models.ArtifactModel.deleted_at.is_not(None))
                    )
                ).scalar_one()
            )
            artifacts_expired = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(models.ArtifactModel)
                        .where(
                            models.ArtifactModel.expires_at.is_not(None),
                            models.ArtifactModel.expires_at <= ts,
                        )
                    )
                ).scalar_one()
            )
            chunk_exists = (
                select(models.ChunkModel.artifact_uid)
                .where(
                    models.ChunkModel.artifact_uid == models.ArtifactModel.artifact_uid
                )
                .exists()
            )
            artifacts_hard_delete_ready = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(models.ArtifactModel)
                        .where(
                            models.ArtifactModel.deleted_at.is_not(None),
                            models.ArtifactModel.deleted_at <= threshold,
                            models.ArtifactModel.reference_count == 0,
                            ~chunk_exists,
                        )
                    )
                ).scalar_one()
            )

            return {
                "evidence_total": evidence_total,
                "evidence_soft_deleted": evidence_soft_deleted,
                "evidence_expired": evidence_expired,
                "evidence_hard_delete_ready": evidence_hard_delete_ready,
                "chunks_total": chunks_total,
                "chunks_soft_deleted": chunks_soft_deleted,
                "chunks_expired": chunks_expired,
                "chunks_hard_delete_ready": chunks_hard_delete_ready,
                "artifacts_total": artifacts_total,
                "artifacts_soft_deleted": artifacts_soft_deleted,
                "artifacts_expired": artifacts_expired,
                "artifacts_hard_delete_ready": artifacts_hard_delete_ready,
            }
