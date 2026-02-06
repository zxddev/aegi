"""OODA 循环相关契约。

定义 Observe/Orient/Decide/Act 各阶段的数据结构。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def generate_uid(prefix: str) -> str:
    """生成带前缀的 UID。"""
    return f"{prefix}_{uuid4().hex[:12]}"


class CredibilityLevel(str, Enum):
    """可信度级别。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ConflictType(str, Enum):
    """冲突类型。"""

    TEMPORAL = "temporal"  # 时间冲突
    FACTUAL = "factual"  # 事实冲突
    SOURCE = "source"  # 来源冲突
    INTERPRETATION = "interpretation"  # 解释冲突


class FactItem(BaseModel):
    """事实条目。

    Observe 阶段从证据中抽取的单条事实。
    """

    fact_id: str = Field(default_factory=lambda: generate_uid("fact"))
    statement: str = Field(min_length=1)
    evidence_uids: list[str] = Field(default_factory=list)
    source: str = ""
    credibility: CredibilityLevel = CredibilityLevel.UNKNOWN
    extracted_at: datetime = Field(default_factory=datetime.now)


class FactChain(BaseModel):
    """事实链。

    Orient 阶段对事实进行组织和关联。
    """

    chain_id: str = Field(default_factory=lambda: generate_uid("chain"))
    facts: list[FactItem] = Field(default_factory=list)
    topic: str = ""
    summary: str = ""
    conflicts: list[str] = Field(default_factory=list)  # 冲突的 fact_id 列表
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class Conflict(BaseModel):
    """冲突记录。

    记录两个事实或假设之间的冲突。
    """

    conflict_id: str = Field(default_factory=lambda: generate_uid("conf"))
    conflict_type: ConflictType
    item_a: str  # fact_id 或 hypothesis_id
    item_b: str
    description: str = ""
    resolution: str | None = None


class Hypothesis(BaseModel):
    """假设。

    Decide 阶段基于事实链生成的假设。
    """

    hypothesis_id: str = Field(default_factory=lambda: generate_uid("hypo"))
    statement: str = Field(min_length=1)
    supporting_facts: list[str] = Field(default_factory=list)  # fact_id 列表
    contradicting_facts: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    reasoning: str = ""


class ObserveOutput(BaseModel):
    """Observe 阶段输出。"""

    facts: list[FactItem] = Field(default_factory=list)
    source_count: int = 0
    evidence_count: int = 0


class OrientOutput(BaseModel):
    """Orient 阶段输出。"""

    fact_chains: list[FactChain] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    summary: str = ""


class DecideOutput(BaseModel):
    """Decide 阶段输出。"""

    hypotheses: list[Hypothesis] = Field(default_factory=list)
    recommended_hypothesis: str | None = None  # hypothesis_id
    gaps: list[str] = Field(default_factory=list)  # 需要补充的证据


class GapFillOutput(BaseModel):
    """补洞检查点输出。

    记录补洞循环的执行结果。
    """

    gaps_detected: list[str] = Field(default_factory=list)
    gaps_resolved: list[str] = Field(default_factory=list)
    new_evidence_count: int = 0
    iterations_used: int = 0
    passed_quality_gate: bool = True


class ActOutput(BaseModel):
    """Act 阶段输出。"""

    action_taken: str = ""
    report_generated: bool = False
    review_triggered: bool = False
    review_id: str | None = None
