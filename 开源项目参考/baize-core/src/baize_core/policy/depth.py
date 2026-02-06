"""动态深度控制。

根据任务复杂度、预算和信息覆盖度自适应调整研究深度。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from baize_core.policy.budget import BudgetTracker


class DepthLevel(str, Enum):
    """研究深度级别。"""

    SHALLOW = "shallow"  # 浅层：快速概览，1-2 轮搜索
    MODERATE = "moderate"  # 中等：标准研究，3-5 轮迭代
    DEEP = "deep"  # 深层：详细调查，5-10 轮迭代
    EXHAUSTIVE = "exhaustive"  # 穷尽：全面覆盖，10+ 轮迭代


class DepthFactor(str, Enum):
    """影响深度的因素。"""

    COMPLEXITY = "complexity"  # 任务复杂度
    BUDGET = "budget"  # 预算约束
    COVERAGE = "coverage"  # 信息覆盖度
    URGENCY = "urgency"  # 紧急程度
    CONFIDENCE = "confidence"  # 当前置信度
    DIVERSITY = "diversity"  # 来源多样性


class DepthConfig(BaseModel):
    """深度配置。"""

    # 初始深度
    initial_level: DepthLevel = Field(
        default=DepthLevel.MODERATE, description="初始深度级别"
    )

    # 各级别的迭代次数范围
    level_iterations: dict[str, tuple[int, int]] = Field(
        default={
            DepthLevel.SHALLOW.value: (1, 2),
            DepthLevel.MODERATE.value: (3, 5),
            DepthLevel.DEEP.value: (5, 10),
            DepthLevel.EXHAUSTIVE.value: (10, 20),
        },
        description="各级别的迭代次数范围",
    )

    # 升级阈值
    upgrade_confidence_threshold: float = Field(
        default=0.3, description="置信度低于此值时升级深度"
    )
    upgrade_coverage_threshold: float = Field(
        default=0.4, description="覆盖度低于此值时升级深度"
    )

    # 降级阈值
    downgrade_confidence_threshold: float = Field(
        default=0.85, description="置信度高于此值时降级深度"
    )
    downgrade_budget_threshold: float = Field(
        default=0.2, description="预算低于此比例时强制降级"
    )

    # 权重
    factor_weights: dict[str, float] = Field(
        default={
            DepthFactor.COMPLEXITY.value: 0.25,
            DepthFactor.BUDGET.value: 0.20,
            DepthFactor.COVERAGE.value: 0.20,
            DepthFactor.CONFIDENCE.value: 0.20,
            DepthFactor.DIVERSITY.value: 0.15,
        },
        description="各因素权重",
    )


class DepthState(BaseModel):
    """深度状态。"""

    current_level: DepthLevel = Field(description="当前深度级别")
    current_iteration: int = Field(default=0, description="当前迭代次数")
    max_iterations: int = Field(description="最大迭代次数")

    # 指标
    complexity_score: float = Field(default=0.5, ge=0, le=1)
    coverage_score: float = Field(default=0.0, ge=0, le=1)
    confidence_score: float = Field(default=0.0, ge=0, le=1)
    diversity_score: float = Field(default=0.0, ge=0, le=1)
    budget_ratio: float = Field(default=1.0, ge=0, le=1)

    # 历史
    level_history: list[tuple[str, datetime]] = Field(default_factory=list)
    adjustment_reasons: list[str] = Field(default_factory=list)


class DepthAdjustment(BaseModel):
    """深度调整建议。"""

    should_adjust: bool = Field(description="是否应该调整")
    new_level: DepthLevel | None = Field(default=None, description="建议的新级别")
    reason: str = Field(description="调整原因")
    continue_research: bool = Field(default=True, description="是否继续研究")


@dataclass
class DepthController:
    """动态深度控制器。

    根据多种因素自适应调整研究深度。
    """

    config: DepthConfig = field(default_factory=DepthConfig)
    budget_tracker: BudgetTracker | None = None

    def initialize_state(
        self,
        complexity_score: float = 0.5,
        initial_level: DepthLevel | None = None,
    ) -> DepthState:
        """初始化深度状态。

        Args:
            complexity_score: 任务复杂度评分（0-1）
            initial_level: 指定的初始级别

        Returns:
            初始深度状态
        """
        level = initial_level or self._compute_initial_level(complexity_score)
        min_iter, max_iter = self.config.level_iterations.get(level.value, (3, 5))

        return DepthState(
            current_level=level,
            current_iteration=0,
            max_iterations=max_iter,
            complexity_score=complexity_score,
            level_history=[(level.value, datetime.now(UTC))],
        )

    def _compute_initial_level(self, complexity: float) -> DepthLevel:
        """根据复杂度计算初始深度。"""
        if complexity < 0.25:
            return DepthLevel.SHALLOW
        elif complexity < 0.5:
            return DepthLevel.MODERATE
        elif complexity < 0.75:
            return DepthLevel.DEEP
        return DepthLevel.EXHAUSTIVE

    def update_metrics(
        self,
        state: DepthState,
        *,
        coverage: float | None = None,
        confidence: float | None = None,
        diversity: float | None = None,
    ) -> DepthState:
        """更新深度状态指标。

        Args:
            state: 当前状态
            coverage: 信息覆盖度
            confidence: 置信度
            diversity: 来源多样性

        Returns:
            更新后的状态
        """
        if coverage is not None:
            state.coverage_score = coverage
        if confidence is not None:
            state.confidence_score = confidence
        if diversity is not None:
            state.diversity_score = diversity

        # 更新预算比例
        if self.budget_tracker is not None:
            budget = self.budget_tracker.to_runtime_budget()
            # 假设初始预算为 10000 token
            initial = 10000
            remaining = budget.token_budget_remaining
            state.budget_ratio = min(1.0, remaining / initial)

        return state

    def evaluate_adjustment(
        self,
        state: DepthState,
    ) -> DepthAdjustment:
        """评估是否需要调整深度。

        Args:
            state: 当前状态

        Returns:
            深度调整建议
        """
        # 检查是否达到最大迭代次数
        if state.current_iteration >= state.max_iterations:
            return DepthAdjustment(
                should_adjust=False,
                reason="已达到最大迭代次数",
                continue_research=False,
            )

        # 预算约束强制降级
        if state.budget_ratio < self.config.downgrade_budget_threshold:
            if state.current_level != DepthLevel.SHALLOW:
                return DepthAdjustment(
                    should_adjust=True,
                    new_level=DepthLevel.SHALLOW,
                    reason=f"预算不足（剩余 {state.budget_ratio:.1%}），强制降级",
                    continue_research=state.current_iteration < 2,
                )
            return DepthAdjustment(
                should_adjust=False,
                reason="预算不足，终止研究",
                continue_research=False,
            )

        # 置信度足够高，考虑降级或终止
        if state.confidence_score >= self.config.downgrade_confidence_threshold:
            if state.coverage_score >= 0.7:
                return DepthAdjustment(
                    should_adjust=False,
                    reason="置信度和覆盖度均已足够",
                    continue_research=False,
                )
            new_level = self._get_lower_level(state.current_level)
            if new_level and new_level != state.current_level:
                return DepthAdjustment(
                    should_adjust=True,
                    new_level=new_level,
                    reason=f"置信度足够（{state.confidence_score:.1%}），降级深度",
                    continue_research=True,
                )

        # 置信度或覆盖度不足，考虑升级
        needs_upgrade = (
            state.confidence_score < self.config.upgrade_confidence_threshold
            or state.coverage_score < self.config.upgrade_coverage_threshold
        )
        if needs_upgrade and state.budget_ratio > 0.5:
            new_level = self._get_higher_level(state.current_level)
            if new_level and new_level != state.current_level:
                return DepthAdjustment(
                    should_adjust=True,
                    new_level=new_level,
                    reason=(
                        f"置信度（{state.confidence_score:.1%}）或"
                        f"覆盖度（{state.coverage_score:.1%}）不足，升级深度"
                    ),
                    continue_research=True,
                )

        return DepthAdjustment(
            should_adjust=False,
            reason="当前深度适当",
            continue_research=True,
        )

    def apply_adjustment(
        self,
        state: DepthState,
        adjustment: DepthAdjustment,
    ) -> DepthState:
        """应用深度调整。

        Args:
            state: 当前状态
            adjustment: 调整建议

        Returns:
            调整后的状态
        """
        if not adjustment.should_adjust or adjustment.new_level is None:
            return state

        state.current_level = adjustment.new_level
        state.level_history.append((adjustment.new_level.value, datetime.now(UTC)))
        state.adjustment_reasons.append(adjustment.reason)

        # 更新最大迭代次数
        _, max_iter = self.config.level_iterations.get(
            adjustment.new_level.value, (3, 5)
        )
        state.max_iterations = max(state.current_iteration + 1, max_iter)

        return state

    def should_continue(self, state: DepthState) -> bool:
        """判断是否应该继续研究。"""
        if state.current_iteration >= state.max_iterations:
            return False
        if state.budget_ratio < 0.1:
            return False
        if state.confidence_score >= 0.9 and state.coverage_score >= 0.8:
            return False
        return True

    def increment_iteration(self, state: DepthState) -> DepthState:
        """增加迭代计数。"""
        state.current_iteration += 1
        return state

    def get_recommended_actions(self, state: DepthState) -> list[str]:
        """获取推荐的下一步动作。"""
        actions = []

        if state.coverage_score < 0.4:
            actions.append("扩大搜索范围，增加更多来源")
        if state.diversity_score < 0.3:
            actions.append("尝试不同类型的来源（新闻、学术、官方）")
        if state.confidence_score < 0.3:
            actions.append("深入验证现有信息，交叉检验")

        if state.current_level == DepthLevel.DEEP:
            actions.append("关注细节和具体证据")
        elif state.current_level == DepthLevel.EXHAUSTIVE:
            actions.append("系统性覆盖所有相关方面")

        return actions if actions else ["继续当前研究方向"]

    def _get_higher_level(self, level: DepthLevel) -> DepthLevel | None:
        """获取更高的深度级别。"""
        order = [
            DepthLevel.SHALLOW,
            DepthLevel.MODERATE,
            DepthLevel.DEEP,
            DepthLevel.EXHAUSTIVE,
        ]
        idx = order.index(level)
        if idx < len(order) - 1:
            return order[idx + 1]
        return None

    def _get_lower_level(self, level: DepthLevel) -> DepthLevel | None:
        """获取更低的深度级别。"""
        order = [
            DepthLevel.SHALLOW,
            DepthLevel.MODERATE,
            DepthLevel.DEEP,
            DepthLevel.EXHAUSTIVE,
        ]
        idx = order.index(level)
        if idx > 0:
            return order[idx - 1]
        return None


def compute_complexity_score(
    *,
    query_length: int,
    entity_count: int,
    time_range_days: int | None,
    requires_synthesis: bool,
    requires_prediction: bool,
) -> float:
    """计算任务复杂度评分。

    Args:
        query_length: 查询长度
        entity_count: 涉及实体数量
        time_range_days: 时间范围（天）
        requires_synthesis: 是否需要综合分析
        requires_prediction: 是否需要预测

    Returns:
        复杂度评分（0-1）
    """
    score = 0.0

    # 查询长度
    if query_length > 100:
        score += 0.15
    elif query_length > 50:
        score += 0.10

    # 实体数量
    if entity_count >= 5:
        score += 0.20
    elif entity_count >= 3:
        score += 0.15
    elif entity_count >= 1:
        score += 0.10

    # 时间范围
    if time_range_days is not None:
        if time_range_days > 365:
            score += 0.20
        elif time_range_days > 30:
            score += 0.15
        elif time_range_days > 7:
            score += 0.10

    # 任务类型
    if requires_synthesis:
        score += 0.25
    if requires_prediction:
        score += 0.20

    return min(1.0, score)


def compute_coverage_score(
    *,
    sources_count: int,
    unique_domains: int,
    topic_aspects_covered: int,
    total_aspects: int,
) -> float:
    """计算信息覆盖度评分。

    Args:
        sources_count: 来源数量
        unique_domains: 唯一域名数量
        topic_aspects_covered: 已覆盖的话题方面数
        total_aspects: 总话题方面数

    Returns:
        覆盖度评分（0-1）
    """
    if total_aspects == 0:
        aspect_ratio = 0.5
    else:
        aspect_ratio = topic_aspects_covered / total_aspects

    source_score = min(1.0, sources_count / 10)
    domain_score = min(1.0, unique_domains / 5)

    return (aspect_ratio * 0.5) + (source_score * 0.25) + (domain_score * 0.25)
