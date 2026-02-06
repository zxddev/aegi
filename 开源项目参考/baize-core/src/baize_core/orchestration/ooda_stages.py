"""OODA 阶段实现。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from baize_core.agents.crew import CrewCoordinator
from baize_core.orchestration.ooda_helpers import (
    assess_credibility,
    build_crew_context,
    calculate_chain_confidence,
    detect_conflicts,
)
from baize_core.orchestration.ooda_types import (
    GapFillerProtocol,
    OodaState,
    QualityGateConfig,
)
from baize_core.orchestration.review import ReviewAgent
from baize_core.schemas.ooda import (
    ActOutput,
    DecideOutput,
    FactChain,
    FactItem,
    GapFillOutput,
    Hypothesis,
    ObserveOutput,
    OrientOutput,
)
from baize_core.validation.constraints import (
    TimelineEvent,
    ValidationReport,
    ValidationResult,
    Z3EventTimelineValidator,
    create_military_validator,
    create_z3_audit_callback,
    extract_timeline_events_from_statements,
)


async def observe_stage(state: OodaState) -> OodaState:
    """Observe 阶段：从证据池组织事实表。"""
    evidence_list = state.get("evidence", [])
    chunks = state.get("chunks", [])
    chunk_map = {c.chunk_uid: c for c in chunks}

    facts: list[FactItem] = []
    for evi in evidence_list:
        credibility = assess_credibility(evi.base_credibility)
        chunk = chunk_map.get(evi.chunk_uid)
        statement = evi.summary or (chunk.text[:200] if chunk else "")
        if statement:
            fact = FactItem(
                statement=statement,
                evidence_uids=[evi.evidence_uid],
                source=evi.source,
                credibility=credibility,
                extracted_at=datetime.now(),
            )
            facts.append(fact)

    observe_output = ObserveOutput(
        facts=facts,
        source_count=len({e.source for e in evidence_list}),
        evidence_count=len(evidence_list),
    )
    return {**state, "observe_output": observe_output}


async def orient_stage(
    state: OodaState, *, crew_agent: CrewCoordinator | None
) -> OodaState:
    """Orient 阶段：生成候选事实链与冲突标记。"""
    observe_output = state.get("observe_output")
    if observe_output is None:
        return {**state, "orient_output": OrientOutput()}

    facts = observe_output.facts
    source_groups: dict[str, list[FactItem]] = defaultdict(list)
    for fact in facts:
        source_groups[fact.source].append(fact)

    fact_chains: list[FactChain] = []
    for source, source_facts in source_groups.items():
        if not source_facts:
            continue
        confidence = calculate_chain_confidence(source_facts)
        chain = FactChain(
            facts=source_facts,
            topic=source,
            summary=f"来自 {source} 的 {len(source_facts)} 条事实",
            confidence=confidence,
        )
        fact_chains.append(chain)

    conflicts = detect_conflicts(facts)

    orient_output = OrientOutput(
        fact_chains=fact_chains,
        conflicts=conflicts,
        summary=f"共 {len(fact_chains)} 个事实链，{len(conflicts)} 处冲突",
    )

    if crew_agent is not None and state.get("task") is not None:
        crew_context = build_crew_context(
            task=state["task"], facts=facts, conflicts=conflicts
        )
        crew_summary = await crew_agent.orient(
            context=crew_context, task_id=state["task"].task_id
        )
        orient_output.summary = (
            f"{orient_output.summary}\n协作摘要：{crew_summary.summary}"
        ).strip()

    return {**state, "orient_output": orient_output}


async def gap_fill_stage(
    state: OodaState,
    *,
    config: QualityGateConfig,
    gap_filler: GapFillerProtocol | None,
) -> OodaState:
    """补洞检查点：处理高优先级证据缺口。"""
    orient_output = state.get("orient_output")
    if orient_output is None:
        return {**state, "gap_fill_output": GapFillOutput(passed_quality_gate=True)}

    detected_gaps: list[str] = []
    for chain in orient_output.fact_chains:
        if chain.confidence < config.min_confidence_threshold:
            detected_gaps.append(f"需要更多来自 {chain.topic} 的可信证据")

    evidence_list = state.get("evidence", [])
    unique_sources = len(set(e.source for e in evidence_list))
    if unique_sources < config.min_source_diversity:
        detected_gaps.append(
            f"来源多样性不足（需要 {config.min_source_diversity}，实际 {unique_sources}）"
        )

    if len(evidence_list) < config.min_evidence_count:
        detected_gaps.append(
            f"证据数量不足（需要 {config.min_evidence_count}，实际 {len(evidence_list)}）"
        )

    if not detected_gaps or gap_filler is None:
        return {
            **state,
            "gap_fill_output": GapFillOutput(
                gaps_detected=detected_gaps,
                passed_quality_gate=len(detected_gaps) == 0,
            ),
        }

    task = state.get("task")
    task_id = task.task_id if task else "unknown"

    new_evidence, resolved_gaps = await gap_filler.fill_gaps(
        gaps=detected_gaps[: config.gap_priority_threshold],
        task_id=task_id,
        max_iterations=config.max_gap_fill_iterations,
    )

    updated_evidence = list(evidence_list) + new_evidence
    remaining_gaps = [g for g in detected_gaps if g not in resolved_gaps]
    passed = len(remaining_gaps) == 0 or len(new_evidence) > 0

    gap_fill_output = GapFillOutput(
        gaps_detected=detected_gaps,
        gaps_resolved=resolved_gaps,
        new_evidence_count=len(new_evidence),
        iterations_used=min(len(detected_gaps), config.max_gap_fill_iterations),
        passed_quality_gate=passed,
    )

    return {
        **state,
        "evidence": updated_evidence,
        "gap_fill_output": gap_fill_output,
    }


async def decide_stage(
    state: OodaState, *, crew_agent: CrewCoordinator | None
) -> OodaState:
    """Decide 阶段：产出结构化决策输入（Hypothesis 列表）。"""
    orient_output = state.get("orient_output")
    if orient_output is None:
        return {**state, "decide_output": DecideOutput()}

    fact_chains = orient_output.fact_chains
    conflicts = orient_output.conflicts

    hypotheses: list[Hypothesis] = []
    gaps: list[str] = []

    for chain in fact_chains:
        if chain.confidence < 0.3:
            gaps.append(f"需要更多来自 {chain.topic} 的可信证据")
            continue

        supporting_facts = [f.fact_id for f in chain.facts]
        contradicting = []
        for conflict in conflicts:
            if conflict.item_a in supporting_facts:
                contradicting.append(conflict.item_b)
            elif conflict.item_b in supporting_facts:
                contradicting.append(conflict.item_a)

        hypothesis = Hypothesis(
            statement=chain.summary,
            supporting_facts=supporting_facts,
            contradicting_facts=contradicting,
            confidence=chain.confidence,
            reasoning=f"基于 {len(chain.facts)} 条事实推断",
        )
        hypotheses.append(hypothesis)

    if not hypotheses:
        gaps.append("证据不足，无法生成有效假设")

    if crew_agent is not None and state.get("task") is not None:
        crew_context = build_crew_context(
            task=state["task"],
            facts=[fact for chain in fact_chains for fact in chain.facts],
            conflicts=conflicts,
        )
        crew_decide = await crew_agent.decide(
            context=crew_context, task_id=state["task"].task_id
        )
        for item in crew_decide.hypotheses:
            hypotheses.append(
                Hypothesis(
                    statement=item,
                    supporting_facts=[],
                    contradicting_facts=[],
                    confidence=0.4,
                    reasoning="协作小组假设",
                )
            )
        if crew_decide.gaps:
            gaps.extend(crew_decide.gaps)

    recommended = None
    if hypotheses:
        best = max(hypotheses, key=lambda h: h.confidence)
        recommended = best.hypothesis_id

    decide_output = DecideOutput(
        hypotheses=hypotheses,
        recommended_hypothesis=recommended,
        gaps=gaps,
    )
    return {**state, "decide_output": decide_output}


async def act_stage(state: OodaState, *, reviewer: ReviewAgent) -> OodaState:
    """Act 阶段：触发审查并记录结果。"""
    decide_output = state.get("decide_output")

    result = reviewer.review(
        claims=state.get("claims", []),
        evidence=state.get("evidence", []),
        chunks=state.get("chunks", []),
        artifacts=state.get("artifacts", []),
        report=state.get("report"),
    )

    action_taken = "审查完成"
    review_triggered = not result.ok

    if decide_output and decide_output.gaps:
        action_taken = f"需要补充证据: {'; '.join(decide_output.gaps)}"
        review_triggered = True

    act_output = ActOutput(
        action_taken=action_taken,
        report_generated=state.get("report") is not None,
        review_triggered=review_triggered,
    )
    return {**state, "review": result, "act_output": act_output}


async def z3_validate_stage(
    state: OodaState,
    *,
    config: QualityGateConfig,
    z3_validator: Z3EventTimelineValidator | None,
) -> OodaState:
    """Z3 校验阶段：执行时间线一致性校验。"""
    if not config.enable_z3_validation:
        return {**state, "z3_validation": None}

    validator = z3_validator
    if validator is None:
        task = state.get("task")
        task_id = task.task_id if task else None
        audit_callback, _ = create_z3_audit_callback(task_id=task_id)
        validator = create_military_validator(audit_callback=audit_callback)

    observe_output = state.get("observe_output")
    events: list[TimelineEvent] = []
    if observe_output:
        statements = [fact.statement for fact in observe_output.facts]
        events = extract_timeline_events_from_statements(
            statements=statements,
            default_entities=["global"],
        )

    if events:
        report = validator.validate_events(events)
    else:
        report = ValidationReport(
            result=ValidationResult.VALID,
            violations=[],
            checked_constraints=0,
            passed_constraints=0,
        )

    return {**state, "z3_validation": report}
