from __future__ import annotations

from baize_core.evidence.validator import EvidenceValidator
from baize_core.schemas.evidence import (
    AnchorType,
    Artifact,
    Chunk,
    ChunkAnchor,
    Claim,
    Evidence,
    Report,
    ReportReference,
)


def test_evidence_validator_missing_links() -> None:
    validator = EvidenceValidator()
    claim = Claim(statement="测试结论", evidence_uids=["evi_missing"])
    result = validator.validate(claims=[claim], evidence=[], chunks=[], artifacts=[])
    assert not result.is_valid
    assert any("Evidence 不存在" in error.message for error in result.errors)


def test_evidence_validator_ok() -> None:
    validator = EvidenceValidator()
    artifact = Artifact(
        content_sha256="sha256:1",
        mime_type="text/html",
        storage_ref="minio://bucket/path",
    )
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
        text="测试",
        text_sha256="sha256:chunk",
    )
    evidence = Evidence(chunk_uid=chunk.chunk_uid, source="source", summary="证据")
    claim = Claim(statement="测试结论", evidence_uids=[evidence.evidence_uid])
    result = validator.validate(
        claims=[claim],
        evidence=[evidence],
        chunks=[chunk],
        artifacts=[artifact],
    )
    assert result.is_valid
    assert result.errors == []


def test_evidence_validator_report_references() -> None:
    validator = EvidenceValidator()
    artifact = Artifact(
        content_sha256="sha256:1",
        mime_type="text/html",
        storage_ref="minio://bucket/path",
        origin_tool="archive_url",
    )
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
        text="测试",
        text_sha256="sha256:chunk",
    )
    evidence = Evidence(chunk_uid=chunk.chunk_uid, source="source", summary="证据")
    report = Report(
        task_id="task-1",
        content_ref="minio://bucket/report",
        references=[
            ReportReference(
                citation=1,
                evidence_uid=evidence.evidence_uid,
                chunk_uid=chunk.chunk_uid,
                artifact_uid=artifact.artifact_uid,
                source_url="https://example.com",
                anchor=chunk.anchor,
            )
        ],
        markdown="报告内容引用 [1]",
    )
    result = validator.validate(
        claims=[],
        evidence=[evidence],
        chunks=[chunk],
        artifacts=[artifact],
        report=report,
    )
    assert result.is_valid
    assert result.errors == []


def test_evidence_validator_requires_conflict_notes() -> None:
    validator = EvidenceValidator()
    artifact = Artifact(
        content_sha256="sha256:1",
        mime_type="text/html",
        storage_ref="minio://bucket/path",
    )
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
        text="测试",
        text_sha256="sha256:chunk",
    )
    evidence = Evidence(
        chunk_uid=chunk.chunk_uid,
        source="source",
        summary="证据",
        conflict_types=["conflict"],
    )
    report = Report(
        task_id="task-1",
        content_ref="minio://bucket/report",
        references=[],
    )
    result = validator.validate(
        claims=[],
        evidence=[evidence],
        chunks=[chunk],
        artifacts=[artifact],
        report=report,
    )
    # 存在冲突但无冲突说明，应该有警告
    assert any("冲突" in error.message for error in result.errors)


def test_evidence_validator_allows_conflict_notes() -> None:
    validator = EvidenceValidator()
    artifact = Artifact(
        content_sha256="sha256:1",
        mime_type="text/html",
        storage_ref="minio://bucket/path",
        origin_tool="archive_url",
    )
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
        text="测试",
        text_sha256="sha256:chunk",
    )
    evidence = Evidence(
        chunk_uid=chunk.chunk_uid,
        source="source",
        summary="证据",
        conflict_types=["conflict"],
    )
    report = Report(
        task_id="task-1",
        content_ref="minio://bucket/report",
        references=[
            ReportReference(
                citation=1,
                evidence_uid=evidence.evidence_uid,
                chunk_uid=chunk.chunk_uid,
                artifact_uid=artifact.artifact_uid,
                source_url="https://example.com",
                anchor=chunk.anchor,
            )
        ],
        conflict_notes="存在冲突说明",
        markdown="报告内容引用 [1]",
    )
    result = validator.validate(
        claims=[],
        evidence=[evidence],
        chunks=[chunk],
        artifacts=[artifact],
        report=report,
    )
    # 有冲突说明，不应该有冲突相关的错误
    assert result.is_valid
    assert not any("冲突" in e.message and "未包含" in e.message for e in result.errors)


def test_evidence_validator_requires_references() -> None:
    validator = EvidenceValidator()
    artifact = Artifact(
        content_sha256="sha256:1",
        mime_type="text/html",
        storage_ref="minio://bucket/path",
        origin_tool="archive_url",
    )
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
        text="测试",
        text_sha256="sha256:chunk",
    )
    evidence = Evidence(chunk_uid=chunk.chunk_uid, source="source", summary="证据")
    report = Report(
        task_id="task-1",
        content_ref="minio://bucket/report",
        references=[],
    )
    result = validator.validate(
        claims=[],
        evidence=[evidence],
        chunks=[chunk],
        artifacts=[artifact],
        report=report,
    )
    assert not result.is_valid
    assert any("报告缺少引用" in error.message for error in result.errors)


def test_evidence_validator_archive_first_required() -> None:
    validator = EvidenceValidator()
    artifact = Artifact(
        content_sha256="sha256:1",
        mime_type="text/html",
        storage_ref="minio://bucket/path",
        origin_tool="web_crawl",
        source_url="https://example.com",
    )
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
        text="测试",
        text_sha256="sha256:chunk",
    )
    evidence = Evidence(
        chunk_uid=chunk.chunk_uid,
        source="source",
        summary="证据",
        uri="https://example.com",
    )
    result = validator.validate(
        claims=[],
        evidence=[evidence],
        chunks=[chunk],
        artifacts=[artifact],
    )
    assert not result.is_valid
    assert any("Archive-First" in error.message for error in result.errors)


def test_evidence_validator_citation_mapping() -> None:
    validator = EvidenceValidator()
    artifact = Artifact(
        content_sha256="sha256:1",
        mime_type="text/html",
        storage_ref="minio://bucket/path",
        origin_tool="archive_url",
    )
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
        text="测试",
        text_sha256="sha256:chunk",
    )
    evidence = Evidence(chunk_uid=chunk.chunk_uid, source="source", summary="证据")
    report = Report(
        task_id="task-1",
        content_ref="minio://bucket/report",
        references=[
            ReportReference(
                citation=2,
                evidence_uid=evidence.evidence_uid,
                chunk_uid=chunk.chunk_uid,
                artifact_uid=artifact.artifact_uid,
                source_url="https://example.com",
                anchor=chunk.anchor,
            )
        ],
        markdown="报告内容引用 [2]",
    )
    result = validator.validate(
        claims=[],
        evidence=[evidence],
        chunks=[chunk],
        artifacts=[artifact],
        report=report,
    )
    assert result.is_valid
    assert result.errors == []
