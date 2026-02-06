"""Critic/Judge 相关契约。

定义质量闸门的输入输出结构。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def generate_critique_id() -> str:
    """生成 Critique ID。"""
    return f"crit_{uuid4().hex[:12]}"


class GapType(str, Enum):
    """证据缺口类型。"""

    MISSING_SOURCE = "missing_source"  # 缺少来源
    INSUFFICIENT_DEPTH = "insufficient_depth"  # 深度不足
    UNVERIFIED_CLAIM = "unverified_claim"  # 未验证的声明
    TEMPORAL_GAP = "temporal_gap"  # 时间覆盖缺口
    GEOGRAPHIC_GAP = "geographic_gap"  # 地理覆盖缺口


class ConflictSeverity(str, Enum):
    """冲突严重程度。"""

    MINOR = "minor"  # 轻微冲突，可忽略
    MODERATE = "moderate"  # 中等冲突，需要说明
    MAJOR = "major"  # 严重冲突，影响结论
    CRITICAL = "critical"  # 关键冲突，需要重新评估


class EvidenceGap(BaseModel):
    """证据缺口。

    Critic 识别的需要补充的证据。
    """

    gap_id: str = Field(default_factory=generate_critique_id)
    gap_type: GapType
    description: str = Field(min_length=1)
    related_claim_ids: list[str] = Field(default_factory=list)
    suggested_query: str = ""  # 建议的补充搜索查询
    priority: int = Field(ge=1, le=5, default=3)  # 1=最高优先级


class EvidenceConflict(BaseModel):
    """证据冲突。

    Judge 识别的证据之间的矛盾。
    """

    conflict_id: str = Field(default_factory=generate_critique_id)
    severity: ConflictSeverity
    evidence_a_uid: str
    evidence_b_uid: str
    description: str = Field(min_length=1)
    resolution: str | None = None
    confidence_impact: float = Field(ge=-1.0, le=0.0, default=-0.1)


class ConfidenceAdjustment(BaseModel):
    """置信度调整。

    Judge 对 Claim 或 Hypothesis 的置信度调整建议。
    """

    target_id: str  # claim_id 或 hypothesis_id
    original_confidence: float = Field(ge=0.0, le=1.0)
    adjusted_confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class Critique(BaseModel):
    """Critic 输出。

    包含证据缺口分析。
    """

    critique_id: str = Field(default_factory=generate_critique_id)
    gaps: list[EvidenceGap] = Field(default_factory=list)
    total_evidence_count: int = 0
    unique_source_count: int = 0
    coverage_score: float = Field(ge=0.0, le=1.0, default=0.0)
    needs_more_evidence: bool = True
    summary: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


class Judgment(BaseModel):
    """Judge 输出。

    包含冲突分析和置信度调整。
    """

    judgment_id: str = Field(default_factory=generate_critique_id)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    adjustments: list[ConfidenceAdjustment] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    has_critical_conflicts: bool = False
    recommendation: str = ""  # 推荐采取的行动
    created_at: datetime = Field(default_factory=datetime.now)


class QualityGateResult(BaseModel):
    """质量闘门结果。

    综合 Critic 和 Judge 的评估结果。
    """

    passed: bool = False
    critique: Critique | None = None
    judgment: Judgment | None = None
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    action_required: str = ""  # "proceed" | "supplement" | "revise" | "reject"
