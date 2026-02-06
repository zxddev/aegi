"""证据链数据结构。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel, Field


def generate_uid(prefix: str) -> str:
    """生成稳定前缀 UID。"""

    return f"{prefix}_{uuid4().hex}"


def generate_deterministic_uid(prefix: str, parts: list[str]) -> str:
    """生成确定性 UID。"""

    payload = "|".join(parts)
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


class AnchorType(str, Enum):
    """锚点类型。"""

    TEXT_OFFSET = "text_offset"
    PDF_PAGE = "pdf_page"
    HTML_XPATH = "html_xpath"


class ChunkAnchor(BaseModel):
    """片段锚点。"""

    type: AnchorType
    ref: str = Field(min_length=1)


class Artifact(BaseModel):
    """原始快照。"""

    artifact_uid: str = ""
    source_url: str | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_sha256: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    storage_ref: str = Field(min_length=1)
    origin_tool: str | None = None
    fetch_trace_id: str | None = None
    license_note: str | None = None

    def model_post_init(self, __context: object) -> None:
        """填充确定性 UID。"""

        if self.artifact_uid:
            return
        self.artifact_uid = generate_deterministic_uid(
            "art",
            [self.source_url or "", self.content_sha256, self.mime_type],
        )


class Chunk(BaseModel):
    """可引用片段。"""

    chunk_uid: str = ""
    artifact_uid: str = Field(min_length=1)
    anchor: ChunkAnchor
    text: str = Field(min_length=1)
    text_sha256: str = Field(min_length=1)

    def model_post_init(self, __context: object) -> None:
        """填充确定性 UID。"""

        if self.chunk_uid:
            return
        self.chunk_uid = generate_deterministic_uid(
            "chk",
            [
                self.artifact_uid,
                f"{self.anchor.type.value}:{self.anchor.ref}",
                self.text_sha256,
            ],
        )


class EvidenceScore(BaseModel):
    """证据评分。"""

    authority: float = Field(ge=0.0, le=1.0)
    timeliness: float = Field(ge=0.0, le=1.0)
    consistency: float = Field(ge=0.0, le=1.0)
    total: float = Field(ge=0.0, le=1.0)


class Evidence(BaseModel):
    """证据记录。"""

    evidence_uid: str = ""
    chunk_uid: str = Field(min_length=1)
    source: str = Field(min_length=1)
    uri: str | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    base_credibility: float = Field(default=0.5, ge=0.0, le=1.0)
    score: EvidenceScore | None = None
    conflict_types: list[str] = Field(default_factory=list)
    conflict_with: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    summary: str | None = None

    def model_post_init(self, __context: object) -> None:
        """填充确定性 UID。"""

        if self.evidence_uid:
            return
        self.evidence_uid = generate_deterministic_uid(
            "evi",
            [
                self.chunk_uid,
                self.source,
                self.uri or "",
            ],
        )


class Claim(BaseModel):
    """结论记录。"""

    claim_uid: str = Field(default_factory=lambda: generate_uid("clm"))
    statement: str = Field(min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_uids: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)


class ReportReference(BaseModel):
    """报告引用映射。"""

    citation: int = Field(ge=1)
    evidence_uid: str = Field(min_length=1)
    chunk_uid: str = Field(min_length=1)
    artifact_uid: str = Field(min_length=1)
    source_url: str | None = None
    anchor: ChunkAnchor


class Report(BaseModel):
    """报告记录。"""

    report_uid: str = Field(default_factory=lambda: generate_uid("rpt"))
    task_id: str = Field(min_length=1)
    outline_uid: str | None = None
    report_type: str | None = None
    content_ref: str = Field(min_length=1)
    references: list[ReportReference] = Field(default_factory=list)
    conflict_notes: str | None = None
    markdown: str | None = None
