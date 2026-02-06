"""证据包导出器。

- 导出格式：manifest.json + artifacts/ + chunks.json + evidence.json
- SHA256 校验
- trace_id 关联
- ZIP 打包
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from baize_core.export.manifest import Manifest, create_manifest
from baize_core.storage import models
from baize_core.storage.postgres import PostgresStore

logger = logging.getLogger(__name__)


@dataclass
class ExportConfig:
    """导出配置。"""

    include_artifacts: bool = True  # 包含原文快照
    include_reports: bool = True  # 包含报告
    compress_level: int = 6  # ZIP 压缩级别 (0-9)
    max_artifact_size: int = 50 * 1024 * 1024  # 单个 Artifact 最大 50MB


@dataclass
class ExportResult:
    """导出结果。"""

    success: bool
    manifest: Manifest
    zip_path: str | None = None
    zip_bytes: bytes | None = None
    error_message: str = ""

    @property
    def total_size(self) -> int:
        """获取总大小。"""
        return self.manifest.get_total_size()


class EvidencePackExporter:
    """证据包导出器。"""

    def __init__(
        self,
        store: PostgresStore,
        config: ExportConfig | None = None,
    ) -> None:
        """初始化导出器。

        Args:
            store: PostgreSQL 存储
            config: 导出配置
        """
        self._store = store
        self._config = config or ExportConfig()

    async def export_task(
        self,
        task_id: str,
        output_path: str | None = None,
    ) -> ExportResult:
        """导出任务的证据包。

        Args:
            task_id: 任务 ID
            output_path: 输出文件路径（可选，不指定则返回字节）

        Returns:
            导出结果
        """
        try:
            # 创建清单
            manifest = create_manifest(task_id=task_id)

            # 加载数据
            artifacts, chunks, evidence, reports = await self._load_task_data(task_id)

            # 更新统计
            manifest.artifact_count = len(artifacts)
            manifest.chunk_count = len(chunks)
            manifest.evidence_count = len(evidence)
            manifest.report_count = len(reports)

            # 创建 ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(
                zip_buffer,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=self._config.compress_level,
            ) as zf:
                # 写入 chunks.json
                chunks_json = json.dumps(
                    [self._serialize_chunk(c) for c in chunks],
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8")
                zf.writestr("chunks.json", chunks_json)
                manifest.add_entry("chunks.json", chunks_json, "application/json")

                # 写入 evidence.json
                evidence_json = json.dumps(
                    [self._serialize_evidence(e) for e in evidence],
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8")
                zf.writestr("evidence.json", evidence_json)
                manifest.add_entry("evidence.json", evidence_json, "application/json")

                # 写入 artifacts/
                if self._config.include_artifacts:
                    for artifact in artifacts:
                        artifact_data = await self._load_artifact_content(artifact)
                        if artifact_data:
                            artifact_path = f"artifacts/{artifact.artifact_uid}"
                            zf.writestr(artifact_path, artifact_data)
                            manifest.add_entry(
                                artifact_path,
                                artifact_data,
                                artifact.content_type or "application/octet-stream",
                            )

                # 写入 reports/
                if self._config.include_reports:
                    for report in reports:
                        report_data = json.dumps(
                            self._serialize_report(report),
                            ensure_ascii=False,
                            indent=2,
                        ).encode("utf-8")
                        report_path = f"reports/{report.report_uid}.json"
                        zf.writestr(report_path, report_data)
                        manifest.add_entry(report_path, report_data, "application/json")

                # 写入 manifest.json（最后写入）
                manifest_json = manifest.to_json().encode("utf-8")
                zf.writestr("manifest.json", manifest_json)

            zip_bytes = zip_buffer.getvalue()

            # 写入文件（如果指定）
            zip_path = None
            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(zip_bytes)
                zip_path = output_path
                logger.info("证据包已导出: %s (%d bytes)", output_path, len(zip_bytes))

            return ExportResult(
                success=True,
                manifest=manifest,
                zip_path=zip_path,
                zip_bytes=zip_bytes if not output_path else None,
            )

        except Exception as exc:
            logger.error("证据包导出失败: %s", exc)
            return ExportResult(
                success=False,
                manifest=Manifest(),
                error_message=str(exc),
            )

    async def _load_task_data(
        self,
        task_id: str,
    ) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
        """加载任务相关数据。"""
        async with self._store.session_factory() as session:
            # 加载 Evidence
            evidence_query = select(models.EvidenceModel)
            task_id_column = getattr(models.EvidenceModel, "task_id", None)
            if task_id_column is not None:
                evidence_query = evidence_query.where(task_id_column == task_id)
            evidence_result = await session.execute(evidence_query)
            evidence = list(evidence_result.scalars().all())

            # 收集 chunk_uid
            chunk_uids = {e.chunk_uid for e in evidence if e.chunk_uid}

            # 加载 Chunks
            chunks = []
            if chunk_uids:
                chunk_result = await session.execute(
                    select(models.ChunkModel).where(
                        models.ChunkModel.chunk_uid.in_(chunk_uids)
                    )
                )
                chunks = list(chunk_result.scalars().all())

            # 收集 artifact_uid
            artifact_uids = {c.artifact_uid for c in chunks if c.artifact_uid}

            # 加载 Artifacts
            artifacts = []
            if artifact_uids:
                artifact_result = await session.execute(
                    select(models.ArtifactModel).where(
                        models.ArtifactModel.artifact_uid.in_(artifact_uids)
                    )
                )
                artifacts = list(artifact_result.scalars().all())

            # 加载 Reports
            report_result = await session.execute(
                select(models.ReportModel).where(models.ReportModel.task_id == task_id)
            )
            reports = list(report_result.scalars().all())

            return artifacts, chunks, evidence, reports

    async def _load_artifact_content(self, artifact: Any) -> bytes | None:
        """加载 Artifact 内容。"""
        if not artifact.storage_ref:
            return None

        # 从 MinIO 加载
        if artifact.storage_ref.startswith("minio://"):
            try:
                from baize_core.config.settings import get_settings
                from baize_core.storage.minio_store import MinIOStore

                settings = get_settings()
                store = MinIOStore(
                    endpoint=settings.minio_endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key,
                )
                await store.connect()
                content = await store.download_content(artifact.storage_ref)
                await store.close()

                # 检查大小限制
                if len(content) > self._config.max_artifact_size:
                    logger.warning(
                        "Artifact 超过大小限制，跳过: %s (%d bytes)",
                        artifact.artifact_uid,
                        len(content),
                    )
                    return None

                return content
            except Exception as exc:
                logger.warning(
                    "加载 Artifact 内容失败: %s - %s", artifact.artifact_uid, exc
                )
                return None

        return None

    def _serialize_chunk(self, chunk: Any) -> dict[str, Any]:
        """序列化 Chunk。"""
        return {
            "chunk_uid": chunk.chunk_uid,
            "artifact_uid": chunk.artifact_uid,
            "text": chunk.text,
            "anchor": {
                "type": chunk.anchor_type,
                "ref": chunk.anchor_ref,
            }
            if chunk.anchor_type
            else None,
            "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
        }

    def _serialize_evidence(self, evidence: Any) -> dict[str, Any]:
        """序列化 Evidence。"""
        return {
            "evidence_uid": evidence.evidence_uid,
            "chunk_uid": evidence.chunk_uid,
            "summary": evidence.summary,
            "confidence": evidence.confidence,
            "extraction_method": evidence.extraction_method,
            "uri": evidence.uri,
            "conflict_types": evidence.conflict_types,
            "conflict_with": evidence.conflict_with,
            "created_at": evidence.created_at.isoformat()
            if evidence.created_at
            else None,
        }

    def _serialize_report(self, report: Any) -> dict[str, Any]:
        """序列化 Report。"""
        return {
            "report_uid": report.report_uid,
            "task_id": report.task_id,
            "outline_uid": report.outline_uid,
            "report_type": report.report_type,
            "content_ref": report.content_ref,
            "conflict_notes": report.conflict_notes,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }


async def export_evidence_pack(
    store: PostgresStore,
    task_id: str,
    output_path: str | None = None,
) -> ExportResult:
    """导出证据包（便捷函数）。

    Args:
        store: PostgreSQL 存储
        task_id: 任务 ID
        output_path: 输出文件路径

    Returns:
        导出结果
    """
    exporter = EvidencePackExporter(store)
    return await exporter.export_task(task_id, output_path)
