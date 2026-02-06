"""Great Expectations 数据质量检查模块。

提供数据质量闸门功能：
- 数据验证规则定义
- 质量检查执行
- 检查报告生成
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ExpectationType(Enum):
    """期望类型。"""

    NOT_NULL = "not_null"
    UNIQUE = "unique"
    IN_SET = "in_set"
    MATCHES_REGEX = "matches_regex"
    BETWEEN = "between"
    LENGTH_BETWEEN = "length_between"
    CUSTOM = "custom"


class CheckResult(Enum):
    """检查结果。"""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class Expectation:
    """数据期望定义。"""

    name: str
    expectation_type: ExpectationType
    column: str
    parameters: dict[str, Any] = field(default_factory=dict)
    severity: str = "error"  # error, warning
    description: str = ""


@dataclass
class CheckDetail:
    """检查详情。"""

    expectation: Expectation
    result: CheckResult
    observed_value: Any = None
    message: str = ""
    unexpected_count: int = 0
    unexpected_percent: float = 0.0


@dataclass
class QualityReport:
    """质量检查报告。"""

    dataset_name: str
    run_time: datetime
    total_expectations: int
    passed_expectations: int
    failed_expectations: int
    success_percent: float
    details: list[CheckDetail]

    @property
    def is_success(self) -> bool:
        """是否全部通过。"""
        return self.failed_expectations == 0


class DataValidator(ABC):
    """数据验证器抽象。"""

    @abstractmethod
    def validate(self, data: list[dict[str, Any]]) -> QualityReport:
        """执行验证。"""


class ExpectationValidator(DataValidator):
    """基于期望的验证器。"""

    def __init__(self, dataset_name: str) -> None:
        """初始化验证器。

        Args:
            dataset_name: 数据集名称
        """
        self._dataset_name = dataset_name
        self._expectations: list[Expectation] = []

    def add_expectation(self, expectation: Expectation) -> None:
        """添加期望。"""
        self._expectations.append(expectation)

    def expect_column_not_null(
        self,
        column: str,
        description: str = "",
    ) -> None:
        """期望列非空。"""
        self._expectations.append(
            Expectation(
                name=f"{column}_not_null",
                expectation_type=ExpectationType.NOT_NULL,
                column=column,
                description=description or f"列 {column} 不应为空",
            )
        )

    def expect_column_unique(
        self,
        column: str,
        description: str = "",
    ) -> None:
        """期望列唯一。"""
        self._expectations.append(
            Expectation(
                name=f"{column}_unique",
                expectation_type=ExpectationType.UNIQUE,
                column=column,
                description=description or f"列 {column} 值应唯一",
            )
        )

    def expect_column_values_in_set(
        self,
        column: str,
        value_set: list[Any],
        description: str = "",
    ) -> None:
        """期望列值在指定集合中。"""
        self._expectations.append(
            Expectation(
                name=f"{column}_in_set",
                expectation_type=ExpectationType.IN_SET,
                column=column,
                parameters={"value_set": value_set},
                description=description or f"列 {column} 值应在 {value_set} 中",
            )
        )

    def expect_column_values_to_match_regex(
        self,
        column: str,
        regex: str,
        description: str = "",
    ) -> None:
        """期望列值匹配正则表达式。"""
        self._expectations.append(
            Expectation(
                name=f"{column}_matches_regex",
                expectation_type=ExpectationType.MATCHES_REGEX,
                column=column,
                parameters={"regex": regex},
                description=description or f"列 {column} 值应匹配 {regex}",
            )
        )

    def expect_column_values_between(
        self,
        column: str,
        min_value: float,
        max_value: float,
        description: str = "",
    ) -> None:
        """期望列值在指定范围内。"""
        self._expectations.append(
            Expectation(
                name=f"{column}_between",
                expectation_type=ExpectationType.BETWEEN,
                column=column,
                parameters={"min_value": min_value, "max_value": max_value},
                description=description
                or f"列 {column} 值应在 {min_value} 到 {max_value} 之间",
            )
        )

    def validate(self, data: list[dict[str, Any]]) -> QualityReport:
        """执行验证。"""
        details: list[CheckDetail] = []
        passed = 0
        failed = 0

        for expectation in self._expectations:
            result = self._check_expectation(expectation, data)
            details.append(result)
            if result.result == CheckResult.PASSED:
                passed += 1
            elif result.result == CheckResult.FAILED:
                failed += 1

        total = len(self._expectations)
        success_percent = (passed / total * 100) if total > 0 else 100.0

        return QualityReport(
            dataset_name=self._dataset_name,
            run_time=datetime.now(UTC),
            total_expectations=total,
            passed_expectations=passed,
            failed_expectations=failed,
            success_percent=success_percent,
            details=details,
        )

    def _check_expectation(
        self,
        expectation: Expectation,
        data: list[dict[str, Any]],
    ) -> CheckDetail:
        """检查单个期望。"""
        column = expectation.column
        values = [row.get(column) for row in data]

        if expectation.expectation_type == ExpectationType.NOT_NULL:
            return self._check_not_null(expectation, values)
        elif expectation.expectation_type == ExpectationType.UNIQUE:
            return self._check_unique(expectation, values)
        elif expectation.expectation_type == ExpectationType.IN_SET:
            return self._check_in_set(expectation, values)
        elif expectation.expectation_type == ExpectationType.MATCHES_REGEX:
            return self._check_regex(expectation, values)
        elif expectation.expectation_type == ExpectationType.BETWEEN:
            return self._check_between(expectation, values)
        else:
            return CheckDetail(
                expectation=expectation,
                result=CheckResult.SKIPPED,
                message="未知的期望类型",
            )

    def _check_not_null(
        self,
        expectation: Expectation,
        values: list[Any],
    ) -> CheckDetail:
        """检查非空。"""
        null_count = sum(1 for v in values if v is None)
        total = len(values)
        unexpected_percent = (null_count / total * 100) if total > 0 else 0.0

        if null_count == 0:
            return CheckDetail(
                expectation=expectation,
                result=CheckResult.PASSED,
                observed_value={"null_count": 0},
            )
        return CheckDetail(
            expectation=expectation,
            result=CheckResult.FAILED,
            observed_value={"null_count": null_count},
            unexpected_count=null_count,
            unexpected_percent=unexpected_percent,
            message=f"发现 {null_count} 个空值",
        )

    def _check_unique(
        self,
        expectation: Expectation,
        values: list[Any],
    ) -> CheckDetail:
        """检查唯一性。"""
        non_null_values = [v for v in values if v is not None]
        unique_count = len(set(non_null_values))
        duplicate_count = len(non_null_values) - unique_count

        if duplicate_count == 0:
            return CheckDetail(
                expectation=expectation,
                result=CheckResult.PASSED,
                observed_value={"unique_count": unique_count},
            )
        return CheckDetail(
            expectation=expectation,
            result=CheckResult.FAILED,
            observed_value={"duplicate_count": duplicate_count},
            unexpected_count=duplicate_count,
            message=f"发现 {duplicate_count} 个重复值",
        )

    def _check_in_set(
        self,
        expectation: Expectation,
        values: list[Any],
    ) -> CheckDetail:
        """检查值集合。"""
        value_set = set(expectation.parameters.get("value_set", []))
        unexpected = [v for v in values if v is not None and v not in value_set]
        unexpected_count = len(unexpected)

        if unexpected_count == 0:
            return CheckDetail(
                expectation=expectation,
                result=CheckResult.PASSED,
            )
        return CheckDetail(
            expectation=expectation,
            result=CheckResult.FAILED,
            observed_value={"unexpected_values": list(set(unexpected))[:10]},
            unexpected_count=unexpected_count,
            message=f"发现 {unexpected_count} 个不在集合中的值",
        )

    def _check_regex(
        self,
        expectation: Expectation,
        values: list[Any],
    ) -> CheckDetail:
        """检查正则匹配。"""
        import re

        pattern = expectation.parameters.get("regex", "")
        regex = re.compile(pattern)
        unexpected = [v for v in values if v is not None and not regex.match(str(v))]
        unexpected_count = len(unexpected)

        if unexpected_count == 0:
            return CheckDetail(
                expectation=expectation,
                result=CheckResult.PASSED,
            )
        return CheckDetail(
            expectation=expectation,
            result=CheckResult.FAILED,
            observed_value={"unexpected_samples": unexpected[:5]},
            unexpected_count=unexpected_count,
            message=f"发现 {unexpected_count} 个不匹配正则的值",
        )

    def _check_between(
        self,
        expectation: Expectation,
        values: list[Any],
    ) -> CheckDetail:
        """检查范围。"""
        min_val = expectation.parameters.get("min_value", float("-inf"))
        max_val = expectation.parameters.get("max_value", float("inf"))
        unexpected = [
            v for v in values if v is not None and (v < min_val or v > max_val)
        ]
        unexpected_count = len(unexpected)

        if unexpected_count == 0:
            return CheckDetail(
                expectation=expectation,
                result=CheckResult.PASSED,
            )
        return CheckDetail(
            expectation=expectation,
            result=CheckResult.FAILED,
            observed_value={"unexpected_samples": unexpected[:5]},
            unexpected_count=unexpected_count,
            message=f"发现 {unexpected_count} 个超出范围的值",
        )


class QualityGate:
    """质量闸门。"""

    def __init__(
        self,
        validator: DataValidator | None = None,
        min_success_percent: float = 100.0,
    ) -> None:
        """初始化质量闸门。

        Args:
            validator: 数据验证器（可选，默认创建标准验证器）
            min_success_percent: 最低通过百分比
        """
        self._validator = validator
        self._min_success_percent = min_success_percent

    def check(self, data: list[dict[str, Any]]) -> tuple[bool, QualityReport]:
        """执行质量检查。

        Args:
            data: 待检查数据

        Returns:
            (是否通过闸门, 质量报告)
        """
        if self._validator is None:
            raise ValueError("未设置验证器")
        report = self._validator.validate(data)
        passed = report.success_percent >= self._min_success_percent
        return passed, report

    def check_artifact(self, artifact: Any) -> EntityCheckResult:
        """检查单个 Artifact。"""
        return ArtifactValidator().validate_entity(artifact)

    def check_evidence(self, evidence: Any) -> EntityCheckResult:
        """检查单个 Evidence。"""
        return EvidenceValidator().validate_entity(evidence)

    def check_chunk(self, chunk: Any) -> EntityCheckResult:
        """检查单个 Chunk。"""
        return ChunkValidator().validate_entity(chunk)


@dataclass
class EntityCheckResult:
    """实体检查结果。"""

    passed: bool
    violations: list[str]
    entity_type: str
    entity_id: str


class EntityValidator(ABC):
    """实体验证器抽象基类。"""

    @abstractmethod
    def validate_entity(self, entity: Any) -> EntityCheckResult:
        """验证单个实体。"""


class ArtifactValidator(EntityValidator):
    """Artifact 验证器。
    校验：
    - storage_ref 必填
    - content_hash 唯一性（通过格式校验）
    - origin_tool 必填
    - fetched_at 必填
    """

    def validate_entity(self, artifact: Any) -> EntityCheckResult:
        """验证 Artifact。"""
        violations: list[str] = []
        artifact_uid = getattr(artifact, "artifact_uid", "unknown")

        # storage_ref 必填
        storage_ref = getattr(artifact, "storage_ref", None)
        if not storage_ref:
            violations.append("storage_ref 不能为空")
        elif not self._is_valid_storage_ref(storage_ref):
            violations.append(f"storage_ref 格式无效: {storage_ref}")

        # content_hash 格式校验（应为 SHA256）
        content_hash = getattr(artifact, "content_hash", None)
        if content_hash and not self._is_valid_hash(content_hash):
            violations.append(
                f"content_hash 格式无效（应为 SHA256）: {content_hash[:20]}..."
            )

        # origin_tool 必填
        origin_tool = getattr(artifact, "origin_tool", None)
        if not origin_tool:
            violations.append("origin_tool 不能为空")

        # fetched_at 必填
        fetched_at = getattr(artifact, "fetched_at", None)
        if fetched_at is None:
            violations.append("fetched_at 不能为空")

        return EntityCheckResult(
            passed=len(violations) == 0,
            violations=violations,
            entity_type="Artifact",
            entity_id=artifact_uid,
        )

    def _is_valid_storage_ref(self, ref: str) -> bool:
        """检查 storage_ref 格式。"""
        valid_prefixes = ("minio://", "s3://", "http://", "https://")
        return any(ref.startswith(p) for p in valid_prefixes)

    def _is_valid_hash(self, hash_str: str) -> bool:
        """检查是否为有效的 SHA256 哈希。"""
        import re

        return bool(re.match(r"^[a-f0-9]{64}$", hash_str.lower()))


class EvidenceValidator(EntityValidator):
    """Evidence 验证器。

    校验：
    - evidence_uid 必填
    - chunk_uid 必填
    - summary 必填
    - confidence 范围 [0, 1]
    - extraction_method 必填
    """

    def validate_entity(self, evidence: Any) -> EntityCheckResult:
        """验证 Evidence。"""
        violations: list[str] = []
        evidence_uid = getattr(evidence, "evidence_uid", "unknown")

        # evidence_uid 必填
        if not evidence_uid or evidence_uid == "unknown":
            violations.append("evidence_uid 不能为空")

        # chunk_uid 必填
        chunk_uid = getattr(evidence, "chunk_uid", None)
        if not chunk_uid:
            violations.append("chunk_uid 不能为空")

        # summary 必填
        summary = getattr(evidence, "summary", None)
        if not summary:
            violations.append("summary 不能为空")

        # confidence 范围校验
        confidence = getattr(evidence, "confidence", None)
        if confidence is not None:
            if not isinstance(confidence, (int, float)):
                violations.append(
                    f"confidence 必须是数值类型，实际: {type(confidence)}"
                )
            elif confidence < 0 or confidence > 1:
                violations.append(
                    f"confidence 必须在 [0, 1] 范围内，实际: {confidence}"
                )

        # extraction_method 必填
        extraction_method = getattr(evidence, "extraction_method", None)
        if not extraction_method:
            violations.append("extraction_method 不能为空")

        return EntityCheckResult(
            passed=len(violations) == 0,
            violations=violations,
            entity_type="Evidence",
            entity_id=evidence_uid,
        )


class ChunkValidator(EntityValidator):
    """Chunk 验证器。

    校验：
    - chunk_uid 必填
    - artifact_uid 必填
    - text 必填
    - anchor 格式校验
    """

    # 有效的锚点类型
    VALID_ANCHOR_TYPES = {
        "line",
        "paragraph",
        "section",
        "page",
        "timestamp",
        "byte_range",
    }

    def validate_entity(self, chunk: Any) -> EntityCheckResult:
        """验证 Chunk。"""
        violations: list[str] = []
        chunk_uid = getattr(chunk, "chunk_uid", "unknown")

        # chunk_uid 必填
        if not chunk_uid or chunk_uid == "unknown":
            violations.append("chunk_uid 不能为空")

        # artifact_uid 必填
        artifact_uid = getattr(chunk, "artifact_uid", None)
        if not artifact_uid:
            violations.append("artifact_uid 不能为空")

        # text 必填
        text = getattr(chunk, "text", None)
        if not text:
            violations.append("text 不能为空")

        # anchor 格式校验
        anchor = getattr(chunk, "anchor", None)
        if anchor:
            anchor_type = getattr(anchor, "type", None)
            anchor_ref = getattr(anchor, "ref", None)

            if anchor_type and anchor_type not in self.VALID_ANCHOR_TYPES:
                violations.append(
                    f"anchor.type 无效: {anchor_type}，有效值: {self.VALID_ANCHOR_TYPES}"
                )

            if anchor_ref is None:
                violations.append("anchor.ref 不能为空")

        return EntityCheckResult(
            passed=len(violations) == 0,
            violations=violations,
            entity_type="Chunk",
            entity_id=chunk_uid,
        )


def create_evidence_chain_validator() -> ExpectationValidator:
    """创建证据链数据验证器（预定义规则）。

    Returns:
        配置好规则的 ExpectationValidator
    """
    validator = ExpectationValidator("evidence_chain")

    # Evidence 规则
    validator.expect_column_not_null("evidence_uid", "Evidence UID 不能为空")
    validator.expect_column_unique("evidence_uid", "Evidence UID 必须唯一")
    validator.expect_column_not_null("chunk_uid", "Evidence 必须关联 Chunk")
    validator.expect_column_not_null("summary", "Evidence 必须有摘要")
    validator.expect_column_values_between(
        "confidence", 0.0, 1.0, "置信度必须在 0-1 范围内"
    )
    validator.expect_column_not_null("extraction_method", "必须记录抽取方法")

    return validator


def create_artifact_validator() -> ExpectationValidator:
    """创建 Artifact 数据验证器。"""
    validator = ExpectationValidator("artifacts")

    # Artifact 规则
    validator.expect_column_not_null("artifact_uid", "Artifact UID 不能为空")
    validator.expect_column_unique("artifact_uid", "Artifact UID 必须唯一")
    validator.expect_column_not_null("storage_ref", "必须有存储引用")
    validator.expect_column_not_null("origin_tool", "必须记录来源工具")
    validator.expect_column_not_null("fetched_at", "必须记录获取时间")
    validator.expect_column_unique("content_hash", "内容哈希应唯一（去重）")

    return validator


def create_chunk_validator() -> ExpectationValidator:
    """创建 Chunk 数据验证器。"""
    validator = ExpectationValidator("chunks")

    # Chunk 规则
    validator.expect_column_not_null("chunk_uid", "Chunk UID 不能为空")
    validator.expect_column_unique("chunk_uid", "Chunk UID 必须唯一")
    validator.expect_column_not_null("artifact_uid", "必须关联 Artifact")
    validator.expect_column_not_null("text", "Chunk 文本不能为空")
    validator.expect_column_values_in_set(
        "anchor_type",
        ["line", "paragraph", "section", "page", "timestamp", "byte_range"],
        "锚点类型必须是有效值",
    )

    return validator
