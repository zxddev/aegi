"""OODA 子图实现。

实现 Observe/Orient/Decide/Act 循环：
- Observe：从证据池组织事实表
- Orient：生成候选事实链与冲突标记
- GapFill：补洞检查点，处理高优先级缺口
- Decide：产出结构化决策输入（Hypothesis 列表）
- Act：触发审查并记录结果
- Z3Validate：时间线一致性校验

支持检查点机制，实现状态持久化与恢复。
支持质量闸门配置。
"""

from __future__ import annotations

from typing import Any

from baize_core.agents.crew import CrewCoordinator
from baize_core.orchestration.ooda_stages import (
    act_stage,
    decide_stage,
    gap_fill_stage,
    observe_stage,
    orient_stage,
    z3_validate_stage,
)
from baize_core.orchestration.ooda_types import (
    GapFillerProtocol,
    OodaState,
    QualityGateConfig,
)
from baize_core.orchestration.review import ReviewAgent
from baize_core.validation.constraints import Z3EventTimelineValidator


def build_ooda_graph(
    reviewer: ReviewAgent,
    crew_agent: CrewCoordinator | None = None,
    checkpointer: Any | None = None,
    quality_gate_config: QualityGateConfig | None = None,
    gap_filler: GapFillerProtocol | None = None,
    z3_validator: Z3EventTimelineValidator | None = None,
) -> object:
    """构建 OODA 子图。"""
    try:
        from langgraph.graph import END, START, StateGraph
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 langgraph") from exc

    config = quality_gate_config or QualityGateConfig()

    async def observe(state: OodaState) -> OodaState:
        return await observe_stage(state)

    async def orient(state: OodaState) -> OodaState:
        return await orient_stage(state, crew_agent=crew_agent)

    async def gap_fill(state: OodaState) -> OodaState:
        return await gap_fill_stage(state, config=config, gap_filler=gap_filler)

    async def decide(state: OodaState) -> OodaState:
        return await decide_stage(state, crew_agent=crew_agent)

    async def act(state: OodaState) -> OodaState:
        return await act_stage(state, reviewer=reviewer)

    async def z3_validate(state: OodaState) -> OodaState:
        return await z3_validate_stage(state, config=config, z3_validator=z3_validator)

    builder = StateGraph(OodaState)
    builder.add_node("observe", observe)
    builder.add_node("orient", orient)
    builder.add_node("gap_fill", gap_fill)
    builder.add_node("decide", decide)
    builder.add_node("act", act)
    builder.add_node("z3_validate", z3_validate)
    builder.add_edge(START, "observe")
    builder.add_edge("observe", "orient")
    builder.add_edge("orient", "gap_fill")
    builder.add_edge("gap_fill", "decide")
    builder.add_edge("decide", "act")
    builder.add_edge("act", "z3_validate")
    builder.add_edge("z3_validate", END)

    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()
