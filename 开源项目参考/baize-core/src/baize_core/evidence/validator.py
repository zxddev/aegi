"""证据链引用完整性校验。

1. 引用存在检查：Claim.evidence_uids[] 非空
2. 链路闭合检查：evidence_uid -> chunk_uid -> artifact_uid -> storage_ref
3. 引用映射一致：正文 [n] 与 references[n] 对应
4. 冲突显式呈现：conflict_types 非空时生成冲突表
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from baize_core.schemas.evidence import Artifact, Chunk, Claim, Evidence, Report


class ValidationSeverity(str, Enum):
    """校验错误严重程度。"""

    ERROR = "error"  # 必须修复
    WARNING = "warning"  # 建议修复
    INFO = "info"  # 信息提示


class ValidationCategory(str, Enum):
    """校验错误类别。"""

    REFERENCE_MISSING = "reference_missing"  # 引用缺失
    CHAIN_BROKEN = "chain_broken"  # 链路断裂
    CITATION_MISMATCH = "citation_mismatch"  # 引用不一致
    CONFLICT_UNHANDLED = "conflict_unhandled"  # 冲突未处理
    ARCHIVE_VIOLATION = "archive_violation"  # Archive-First 违规
    STORAGE_INVALID = "storage_invalid"  # 存储引用无效


@dataclass(frozen=True)
class ValidationError:
    """校验错误。"""

    message: str
    claim_uid: str | None = None
    evidence_uid: str | None = None
    category: ValidationCategory = ValidationCategory.REFERENCE_MISSING
    severity: ValidationSeverity = ValidationSeverity.ERROR
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConflictEntry:
    """冲突记录条目。"""

    evidence_uid: str
    conflict_types: list[str]
    conflict_with: list[str]
    summary: str


@dataclass
class ConflictTable:
    """冲突表（用于报告呈现）。"""

    entries: list[ConflictEntry]
    total_conflicts: int

    def to_markdown(self) -> str:
        """生成 Markdown 格式的冲突表。"""
        if not self.entries:
            return ""

        lines = [
            "## 证据冲突表",
            "",
            "说明：冲突证据会影响相关结论的置信度，输出时必须显式标注并谨慎表述。",
            "",
            "| 冲突双方 | 冲突类型 | 严重程度 | 摘要 |",
            "|----------|----------|----------|------|",
        ]
        for entry in self.entries:
            severity = _infer_conflict_severity(
                conflict_types=entry.conflict_types,
                conflict_with=entry.conflict_with,
            )
            conflict_types = ", ".join(entry.conflict_types)
            conflict_with = ", ".join(entry.conflict_with[:3])  # 最多显示3个
            if len(entry.conflict_with) > 3:
                conflict_with += f"... (+{len(entry.conflict_with) - 3})"
            summary = (
                entry.summary[:50] + "..." if len(entry.summary) > 50 else entry.summary
            )
            parties = f"{entry.evidence_uid[:12]}... ↔ {conflict_with or '(unknown)'}"
            lines.append(f"| {parties} | {conflict_types} | {severity} | {summary} |")

        lines.append("")
        lines.append(f"共 {self.total_conflicts} 处冲突")
        return "\n".join(lines)


def _infer_conflict_severity(
    *, conflict_types: list[str], conflict_with: list[str]
) -> str:
    """按确定性规则估计冲突严重程度。"""

    normalized = " ".join(conflict_types).lower()
    if "critical" in normalized or "关键" in normalized:
        return "critical"
    if any(
        key in normalized for key in ("timeline", "temporal", "time", "因果", "causal")
    ):
        return "major"
    if len(conflict_types) >= 3 or len(conflict_with) >= 3:
        return "major"
    if len(conflict_types) >= 2:
        return "moderate"
    return "minor"


@dataclass
class ValidationResult:
    """完整校验结果。"""

    errors: list[ValidationError]
    conflict_table: ConflictTable | None = None
    is_valid: bool = True
    summary: str = ""

    @property
    def error_count(self) -> int:
        """错误数量（不含警告和信息）。"""
        return sum(1 for e in self.errors if e.severity == ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """警告数量。"""
        return sum(1 for e in self.errors if e.severity == ValidationSeverity.WARNING)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "is_valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "summary": self.summary,
            "errors": [
                {
                    "message": e.message,
                    "category": e.category.value,
                    "severity": e.severity.value,
                    "claim_uid": e.claim_uid,
                    "evidence_uid": e.evidence_uid,
                    "details": e.details,
                }
                for e in self.errors
            ],
            "conflict_table": self.conflict_table.to_markdown()
            if self.conflict_table
            else None,
        }


class EvidenceValidator:
    """证据链校验器。

    执行引用完整性校验：
    1. 引用存在检查
    2. 链路闭合检查
    3. 引用映射一致检查
    4. 冲突显式呈现
    5. Archive-First 规则检查
    6. Storage-ref 有效性检查
    """

    def validate(
        self,
        *,
        claims: list[Claim],
        evidence: list[Evidence],
        chunks: list[Chunk],
        artifacts: list[Artifact],
        report: Report | None = None,
    ) -> ValidationResult:
        """验证引用链路是否闭合。

        Args:
            claims: 结论列表
            evidence: 证据列表
            chunks: 片段列表
            artifacts: 原文快照列表
            report: 报告（可选）

        Returns:
            完整校验结果
        """
        errors: list[ValidationError] = []
        evidence_map = {item.evidence_uid: item for item in evidence}
        chunk_map = {item.chunk_uid: item for item in chunks}
        artifact_map = {item.artifact_uid: item for item in artifacts}

        # 1. 报告引用检查
        if report is not None and not report.references:
            errors.append(
                ValidationError(
                    "报告缺少引用",
                    category=ValidationCategory.REFERENCE_MISSING,
                    severity=ValidationSeverity.ERROR,
                )
            )

        # 2. 正文引用标注检查
        if report is not None and report.markdown:
            errors.extend(self._validate_citations(report))

        # 3. 冲突检查与冲突表生成
        conflict_table = self._build_conflict_table(evidence, evidence_map)
        if conflict_table and conflict_table.entries:
            if report is None or not (report.conflict_notes or "").strip():
                errors.append(
                    ValidationError(
                        f"存在 {conflict_table.total_conflicts} 处证据冲突，但报告未包含冲突说明",
                        category=ValidationCategory.CONFLICT_UNHANDLED,
                        severity=ValidationSeverity.WARNING,
                        details={"conflict_count": conflict_table.total_conflicts},
                    )
                )

        # 4. Claim 引用链路检查
        for claim in claims:
            errors.extend(
                self._validate_claim_chain(
                    claim=claim,
                    evidence_map=evidence_map,
                    chunk_map=chunk_map,
                    artifact_map=artifact_map,
                )
            )

        # 5. 对于未被 claim 引用的 evidence，也需要校验链路完整性
        if not claims:
            for ev in evidence:
                errors.extend(
                    self._validate_evidence_chain(
                        evidence_item=ev,
                        chunk_map=chunk_map,
                        artifact_map=artifact_map,
                    )
                )

        # 6. 报告引用校验
        if report is not None:
            errors.extend(
                self._validate_report_references(
                    report=report,
                    evidence_map=evidence_map,
                    chunk_map=chunk_map,
                    artifact_map=artifact_map,
                )
            )

        # 7. Storage-ref 有效性检查
        for artifact in artifacts:
            errors.extend(self._validate_storage_ref(artifact))

        # 构建结果
        is_valid = not any(e.severity == ValidationSeverity.ERROR for e in errors)
        error_count = sum(1 for e in errors if e.severity == ValidationSeverity.ERROR)
        warning_count = sum(
            1 for e in errors if e.severity == ValidationSeverity.WARNING
        )
        summary = f"校验完成：{error_count} 个错误，{warning_count} 个警告"

        return ValidationResult(
            errors=errors,
            conflict_table=conflict_table
            if conflict_table and conflict_table.entries
            else None,
            is_valid=is_valid,
            summary=summary,
        )

    def validate_legacy(
        self,
        *,
        claims: list[Claim],
        evidence: list[Evidence],
        chunks: list[Chunk],
        artifacts: list[Artifact],
        report: Report | None = None,
    ) -> list[ValidationError]:
        """兼容旧版接口，返回错误列表。"""
        result = self.validate(
            claims=claims,
            evidence=evidence,
            chunks=chunks,
            artifacts=artifacts,
            report=report,
        )
        return result.errors

    def _validate_claim_chain(
        self,
        *,
        claim: Claim,
        evidence_map: dict[str, Evidence],
        chunk_map: dict[str, Chunk],
        artifact_map: dict[str, Artifact],
    ) -> list[ValidationError]:
        """校验 Claim 的引用链路。"""
        errors: list[ValidationError] = []

        if not claim.evidence_uids:
            errors.append(
                ValidationError(
                    "Claim 缺少证据引用",
                    claim_uid=claim.claim_uid,
                    category=ValidationCategory.REFERENCE_MISSING,
                    severity=ValidationSeverity.ERROR,
                )
            )
            return errors

        for evidence_uid in claim.evidence_uids:
            ev = evidence_map.get(evidence_uid)
            if ev is None:
                errors.append(
                    ValidationError(
                        "Evidence 不存在",
                        claim_uid=claim.claim_uid,
                        evidence_uid=evidence_uid,
                        category=ValidationCategory.CHAIN_BROKEN,
                        severity=ValidationSeverity.ERROR,
                    )
                )
                continue

            chunk = chunk_map.get(ev.chunk_uid)
            if chunk is None:
                errors.append(
                    ValidationError(
                        f"Chunk 不存在: {ev.chunk_uid}",
                        claim_uid=claim.claim_uid,
                        evidence_uid=evidence_uid,
                        category=ValidationCategory.CHAIN_BROKEN,
                        severity=ValidationSeverity.ERROR,
                    )
                )
                continue

            if chunk.artifact_uid not in artifact_map:
                errors.append(
                    ValidationError(
                        f"Artifact 不存在: {chunk.artifact_uid}",
                        claim_uid=claim.claim_uid,
                        evidence_uid=evidence_uid,
                        category=ValidationCategory.CHAIN_BROKEN,
                        severity=ValidationSeverity.ERROR,
                    )
                )
            else:
                errors.extend(
                    self._validate_archive_first(
                        evidence_item=ev,
                        artifact=artifact_map[chunk.artifact_uid],
                    )
                )

        return errors

    def _validate_evidence_chain(
        self,
        *,
        evidence_item: Evidence,
        chunk_map: dict[str, Chunk],
        artifact_map: dict[str, Artifact],
    ) -> list[ValidationError]:
        """校验单个 Evidence 的链路完整性。"""
        errors: list[ValidationError] = []

        chunk = chunk_map.get(evidence_item.chunk_uid)
        if chunk is None:
            errors.append(
                ValidationError(
                    f"Evidence 引用的 Chunk 不存在: {evidence_item.chunk_uid}",
                    evidence_uid=evidence_item.evidence_uid,
                    category=ValidationCategory.CHAIN_BROKEN,
                    severity=ValidationSeverity.ERROR,
                )
            )
            return errors

        artifact = artifact_map.get(chunk.artifact_uid)
        if artifact is None:
            errors.append(
                ValidationError(
                    f"Chunk 引用的 Artifact 不存在: {chunk.artifact_uid}",
                    evidence_uid=evidence_item.evidence_uid,
                    category=ValidationCategory.CHAIN_BROKEN,
                    severity=ValidationSeverity.ERROR,
                )
            )
            return errors

        errors.extend(
            self._validate_archive_first(
                evidence_item=evidence_item,
                artifact=artifact,
            )
        )

        return errors

    def _validate_report_references(
        self,
        *,
        report: Report,
        evidence_map: dict[str, Evidence],
        chunk_map: dict[str, Chunk],
        artifact_map: dict[str, Artifact],
    ) -> list[ValidationError]:
        """校验报告引用的完整性。"""
        errors: list[ValidationError] = []

        for reference in report.references:
            ref_evidence = evidence_map.get(reference.evidence_uid)
            if ref_evidence is None:
                errors.append(
                    ValidationError(
                        f"报告引用的 Evidence 不存在: {reference.evidence_uid}",
                        evidence_uid=reference.evidence_uid,
                        category=ValidationCategory.CHAIN_BROKEN,
                        severity=ValidationSeverity.ERROR,
                        details={"citation": reference.citation},
                    )
                )
                continue

            ref_chunk = chunk_map.get(reference.chunk_uid)
            if ref_chunk is None:
                errors.append(
                    ValidationError(
                        f"报告引用的 Chunk 不存在: {reference.chunk_uid}",
                        evidence_uid=reference.evidence_uid,
                        category=ValidationCategory.CHAIN_BROKEN,
                        severity=ValidationSeverity.ERROR,
                        details={"citation": reference.citation},
                    )
                )
                continue

            if ref_chunk.artifact_uid != reference.artifact_uid:
                errors.append(
                    ValidationError(
                        "报告引用的 Artifact 与 Chunk 不匹配",
                        evidence_uid=reference.evidence_uid,
                        category=ValidationCategory.CITATION_MISMATCH,
                        severity=ValidationSeverity.ERROR,
                        details={
                            "citation": reference.citation,
                            "expected": ref_chunk.artifact_uid,
                            "actual": reference.artifact_uid,
                        },
                    )
                )
                continue

            if reference.artifact_uid not in artifact_map:
                errors.append(
                    ValidationError(
                        f"报告引用的 Artifact 不存在: {reference.artifact_uid}",
                        evidence_uid=reference.evidence_uid,
                        category=ValidationCategory.CHAIN_BROKEN,
                        severity=ValidationSeverity.ERROR,
                        details={"citation": reference.citation},
                    )
                )
                continue

            # 校验锚点一致性
            if (
                ref_chunk.anchor.type != reference.anchor.type
                or ref_chunk.anchor.ref != reference.anchor.ref
            ):
                errors.append(
                    ValidationError(
                        "报告引用锚点与 Chunk 不一致",
                        evidence_uid=reference.evidence_uid,
                        category=ValidationCategory.CITATION_MISMATCH,
                        severity=ValidationSeverity.WARNING,
                        details={
                            "citation": reference.citation,
                            "chunk_anchor": {
                                "type": ref_chunk.anchor.type,
                                "ref": ref_chunk.anchor.ref,
                            },
                            "ref_anchor": {
                                "type": reference.anchor.type,
                                "ref": reference.anchor.ref,
                            },
                        },
                    )
                )
            else:
                errors.extend(
                    self._validate_archive_first(
                        evidence_item=ref_evidence,
                        artifact=artifact_map[reference.artifact_uid],
                    )
                )

        return errors

    def _build_conflict_table(
        self,
        evidence: list[Evidence],
        evidence_map: dict[str, Evidence],
    ) -> ConflictTable | None:
        """构建冲突表。"""
        entries: list[ConflictEntry] = []
        total_conflicts = 0

        for ev in evidence:
            if ev.conflict_types:
                total_conflicts += len(ev.conflict_types)
                entries.append(
                    ConflictEntry(
                        evidence_uid=ev.evidence_uid,
                        conflict_types=list(ev.conflict_types),
                        conflict_with=list(ev.conflict_with)
                        if ev.conflict_with
                        else [],
                        summary=ev.summary or "",
                    )
                )

        if not entries:
            return None

        return ConflictTable(entries=entries, total_conflicts=total_conflicts)

    def _validate_storage_ref(self, artifact: Artifact) -> list[ValidationError]:
        """校验 Artifact 的 storage_ref 有效性。"""
        errors: list[ValidationError] = []

        if not artifact.storage_ref:
            errors.append(
                ValidationError(
                    f"Artifact 缺少 storage_ref: {artifact.artifact_uid}",
                    category=ValidationCategory.STORAGE_INVALID,
                    severity=ValidationSeverity.ERROR,
                    details={"artifact_uid": artifact.artifact_uid},
                )
            )
            return errors

        # 校验 storage_ref 格式（minio://bucket/path 或 http(s)://）
        valid_prefixes = ("minio://", "http://", "https://", "s3://")
        if not any(artifact.storage_ref.startswith(p) for p in valid_prefixes):
            errors.append(
                ValidationError(
                    f"Artifact storage_ref 格式无效: {artifact.storage_ref}",
                    category=ValidationCategory.STORAGE_INVALID,
                    severity=ValidationSeverity.WARNING,
                    details={
                        "artifact_uid": artifact.artifact_uid,
                        "storage_ref": artifact.storage_ref,
                    },
                )
            )

        return errors

    def _validate_archive_first(
        self,
        *,
        evidence_item: Evidence,
        artifact: Artifact,
    ) -> list[ValidationError]:
        """校验 Archive-First 规则。"""

        if not evidence_item.uri:
            return []
        if artifact.origin_tool != "archive_url":
            return [
                ValidationError(
                    "Evidence 未通过 Archive-First 归档",
                    evidence_uid=evidence_item.evidence_uid,
                )
            ]
        return []

    def _validate_citations(self, report: Report) -> list[ValidationError]:
        """校验正文引用标注与 references 一致性。"""

        errors: list[ValidationError] = []
        if not report.markdown:
            return errors

        citations_in_text = self._extract_citations(report.markdown)
        if not citations_in_text:
            errors.append(ValidationError("报告正文缺少引用标注"))
            return errors

        reference_citations = [ref.citation for ref in report.references]
        if len(set(reference_citations)) != len(reference_citations):
            errors.append(ValidationError("报告引用编号重复"))

        reference_set = set(reference_citations)
        missing_refs = sorted(citations_in_text - reference_set)
        if missing_refs:
            errors.append(
                ValidationError(
                    f"报告引用缺失编号: {', '.join(str(item) for item in missing_refs)}"
                )
            )

        missing_in_text = sorted(reference_set - citations_in_text)
        if missing_in_text:
            errors.append(
                ValidationError(
                    "报告引用未在正文出现: "
                    + ", ".join(str(item) for item in missing_in_text)
                )
            )
        return errors

    @staticmethod
    def _extract_citations(markdown: str) -> set[int]:
        """提取正文中的引用编号。"""

        matches = re.findall(r"\[(\d+)\]", markdown)
        return {int(item) for item in matches}
