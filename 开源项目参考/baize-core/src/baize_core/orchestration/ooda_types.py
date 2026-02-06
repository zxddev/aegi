"""OODA 类型定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypedDict

from baize_core.schemas.evidence import Artifact, Chunk, Claim, Evidence, Report
from baize_core.schemas.ooda import (
    ActOutput,
    DecideOutput,
    GapFillOutput,
    ObserveOutput,
    OrientOutput,
)
from baize_core.schemas.review import ReviewResult
from baize_core.schemas.task import TaskSpec
from baize_core.validation.constraints import ValidationReport


@dataclass
class QualityGateConfig:
    """质量闸门配置。

    控制 OODA 循环的质量门限。
    """

    # 最小证据数量
    min_evidence_count: int = 3
    # 最小来源多样性（不同来源的数量）
    min_source_diversity: int = 2
    # 最小置信度阈值
    min_confidence_threshold: float = 0.5
    # 缺口优先级阈值（只处理 priority <= N 的缺口）
    gap_priority_threshold: int = 2
    # 补洞最大迭代次数
    max_gap_fill_iterations: int = 2
    # 是否启用 Z3 时间线校验
    enable_z3_validation: bool = True
    # Z3 校验失败是否阻塞
    z3_validation_blocking: bool = False


class GapFillerProtocol(Protocol):
    """补洞器协议。"""

    async def fill_gaps(
        self,
        gaps: list[str],
        task_id: str,
        max_iterations: int,
    ) -> tuple[list[Evidence], list[str]]:
        """填补证据缺口。"""


class OodaState(TypedDict):
    """OODA 状态。"""

    task: TaskSpec
    evidence: list[Evidence]
    claims: list[Claim]
    chunks: list[Chunk]
    artifacts: list[Artifact]
    report: Report | None
    review: ReviewResult | None

    # OODA 阶段输出
    observe_output: ObserveOutput | None
    orient_output: OrientOutput | None
    gap_fill_output: GapFillOutput | None
    decide_output: DecideOutput | None
    act_output: ActOutput | None

    # Z3 校验结果
    z3_validation: ValidationReport | None
