"""OODA 辅助函数。"""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse

from baize_core.llm.prompt_builder import PromptBuilder
from baize_core.schemas.content import ContentSource
from baize_core.schemas.ooda import (
    Conflict,
    ConflictType,
    CredibilityLevel,
    FactItem,
)
from baize_core.schemas.task import TaskSpec


def build_crew_context(
    *, task: TaskSpec, facts: list[FactItem], conflicts: list[Conflict]
) -> str:
    """构建协作上下文。"""
    fact_lines = [
        f"- {fact.statement} (source={fact.source}, cred={fact.credibility.value})"
        for fact in facts
    ]
    conflict_lines = [
        f"- {conflict.description} ({conflict.conflict_type.value})"
        for conflict in conflicts
        if conflict.description
    ]
    facts_block = "\n".join(fact_lines) if fact_lines else "- (无事实)"
    conflicts_block = "\n".join(conflict_lines) if conflict_lines else "- (无冲突记录)"
    prompt = (
        PromptBuilder()
        .add_user_query(
            f"任务目标：{task.objective}\n输出要求：结构化总结、谨慎表述、避免臆测。",
            source_type=ContentSource.INTERNAL,
            source_ref="ooda_crew_query",
        )
        .add_evidence(
            f"事实列表：\n{facts_block}",
            source_ref="ooda_facts",
            content_type="facts",
        )
        .add_evidence(
            f"冲突列表：\n{conflicts_block}",
            source_ref="ooda_conflicts",
            content_type="conflicts",
        )
        .build()
    )
    return next((m["content"] for m in prompt.messages if m["role"] == "user"), "")


def assess_credibility(base_credibility: float) -> CredibilityLevel:
    """评估可信度级别。"""
    if base_credibility >= 0.7:
        return CredibilityLevel.HIGH
    if base_credibility >= 0.4:
        return CredibilityLevel.MEDIUM
    if base_credibility > 0:
        return CredibilityLevel.LOW
    return CredibilityLevel.UNKNOWN


def calculate_chain_confidence(facts: list[FactItem]) -> float:
    """计算事实链的置信度。"""
    if not facts:
        return 0.0

    credibility_scores = {
        CredibilityLevel.HIGH: 0.9,
        CredibilityLevel.MEDIUM: 0.6,
        CredibilityLevel.LOW: 0.3,
        CredibilityLevel.UNKNOWN: 0.1,
    }

    total = sum(credibility_scores.get(f.credibility, 0.1) for f in facts)
    return total / len(facts)


def detect_conflicts(facts: list[FactItem]) -> list[Conflict]:
    """检测事实之间的冲突。"""
    conflicts: list[Conflict] = []

    # 按域名分组
    domain_facts: dict[str, list[FactItem]] = defaultdict(list)
    for fact in facts:
        domain = extract_domain(fact.source)
        domain_facts[domain].append(fact)

    # 检测高/低可信度来源之间的冲突
    high_cred_facts = [f for f in facts if f.credibility == CredibilityLevel.HIGH]
    low_cred_facts = [f for f in facts if f.credibility == CredibilityLevel.LOW]

    for high_fact in high_cred_facts:
        for low_fact in low_cred_facts:
            if high_fact.source != low_fact.source:
                conflict = Conflict(
                    conflict_type=ConflictType.SOURCE,
                    item_a=high_fact.fact_id,
                    item_b=low_fact.fact_id,
                    description=(
                        f"高可信来源 ({high_fact.source}) 与低可信来源 "
                        f"({low_fact.source}) 可能存在冲突"
                    ),
                )
                conflicts.append(conflict)

    return conflicts


def extract_domain(source: str) -> str:
    """从来源提取域名。"""
    if source.startswith(("http://", "https://")):
        parsed = urlparse(source)
        return parsed.netloc or source
    return source
