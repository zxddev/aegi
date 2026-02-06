"""STORM 任务模板。"""

from __future__ import annotations

from typing import Any

from baize_core.schemas.storm import (
    SUMMARY_SECTION_DEPTH_POLICY,
    CoverageItem,
    DepthPolicy,
    ReportConfig,
    SectionType,
    StormSectionSpec,
    StormTaskType,
)
from baize_core.llm.runner import LlmRunner
from baize_core.modules.parser import UserInputParser
from baize_core.modules.registry import ModuleRegistry


def build_coverage_checklist(task_type: StormTaskType) -> list[CoverageItem]:
    """构建覆盖清单。"""

    if task_type == StormTaskType.STRATEGIC_SITUATION:
        questions = [
            "核心态势与战略目标是什么？",
            "关键参与方与权力结构如何？",
            "近期关键事件与时间线如何演变？",
            "能力对比与资源配置是什么？",
            "地理/基础设施要素对态势的影响是什么？",
            "主要不确定性与信息缺口是什么？",
            "可能的演化路径与触发条件是什么？",
        ]
    else:
        questions = [
            "行动目标与作战假设是什么？",
            "关键部队与编成要素有哪些？",
            "行动时间线与关键窗口是什么？",
            "地理与后勤约束是什么？",
            "敌我能力与意图对比如何？",
            "高风险点与不确定性是什么？",
            "可能的行动分支与触发条件是什么？",
        ]
    return [CoverageItem(question=question) for question in questions]


def build_default_depth_policy(task_type: StormTaskType) -> DepthPolicy:
    """构建默认深挖策略。
    
    优化配置说明：
    - max_results=5: 每章节最多 5 个搜索结果，平衡质量与速度
    - max_iterations=1: 单轮研究，避免重复抓取
    - min_sources=2: 降低最低来源要求，减少"证据不足"
    """

    if task_type == StormTaskType.STRATEGIC_SITUATION:
        return DepthPolicy(min_sources=2, max_iterations=1, max_results=5)
    return DepthPolicy(min_sources=2, max_iterations=1, max_results=5)


def build_outline_sections(
    *,
    task_type: StormTaskType,
    coverage: list[CoverageItem],
) -> list[StormSectionSpec]:
    """构建大纲章节。"""

    coverage_ids = [item.item_id for item in coverage]
    depth_policy = build_default_depth_policy(task_type)
    if task_type == StormTaskType.STRATEGIC_SITUATION:
        titles = [
            "战略背景与态势",
            "关键参与方与能力",
            "时间线与关键事件",
            "地理与基础设施影响",
            "风险点与情景演化",
        ]
        questions = [
            "当前态势的核心驱动因素是什么？",
            "关键参与方的意图与能力对比如何？",
            "近期关键事件及其影响是什么？",
            "地理/基础设施如何影响态势？",
            "潜在风险与演化路径有哪些？",
        ]
    else:
        titles = [
            "行动目标与作战假设",
            "关键部队与行动编组",
            "时间线与关键窗口",
            "地理与后勤约束",
            "风险点与行动分支",
        ]
        questions = [
            "行动目标与作战假设是什么？",
            "关键部队与编组能力如何？",
            "时间线与关键窗口如何约束行动？",
            "地理与后勤因素如何影响行动？",
            "高风险点与潜在分支是什么？",
        ]
    sections = []
    for idx, (title, question) in enumerate(
        zip(titles, questions, strict=False), start=1
    ):
        sections.append(
            StormSectionSpec(
                title=title,
                question=question,
                coverage_item_ids=coverage_ids[max(0, idx - 2) : idx + 1],
                depth_policy=depth_policy,
            )
        )

    # 为战略态势任务添加观察指标章节
    if task_type == StormTaskType.STRATEGIC_SITUATION:
        sections.append(
            StormSectionSpec(
                title="观察指标（Watchlist）",
                question="需要持续关注的态势信号和预警指标有哪些？",
                coverage_item_ids=[],  # 独立章节，不关联覆盖清单
                depth_policy=SUMMARY_SECTION_DEPTH_POLICY,
                section_type=SectionType.WATCHLIST,
            )
        )

    return sections


async def build_outline_sections_from_config(
    *,
    task_id: str,
    report_config: ReportConfig,
    module_registry: ModuleRegistry,
    input_parser: UserInputParser | None = None,
    llm_runner: LlmRunner | None = None,
) -> tuple[list[StormSectionSpec], list[CoverageItem]]:
    """从 ReportConfig 构建章节列表（核心变更）。"""

    # 1) 预设模块 → sections + coverage
    sections, coverage = await module_registry.resolve_config(report_config)

    # 2) 用户自由输入 → 解析为 sections
    for item in report_config.custom_sections:
        if not isinstance(item, dict):
            continue

        content: Any = (
            item.get("content")
            or item.get("text")
            or item.get("input")
            or item.get("query")
        )
        if not isinstance(content, str) or not content.strip():
            # 允许直接传入 {title, question}
            title = item.get("title")
            question = item.get("question")
            if isinstance(title, str) and isinstance(question, str):
                sections.append(
                    StormSectionSpec(title=title.strip(), question=question.strip())
                )
            continue

        if input_parser is not None and llm_runner is not None:
            parsed = await input_parser.parse_to_sections(
                content.strip(),
                llm_runner,
                task_id=task_id,
            )
            sections.extend(parsed)
        else:
            # 无解析器时降级：将内容作为单章节问题
            sections.append(
                StormSectionSpec(title="用户自定义章节", question=content.strip())
            )

    # 3) 最小保障：至少一个章节
    if not sections:
        sections.append(
            StormSectionSpec(
                title="综合分析",
                question="请基于证据对任务目标进行综合分析，并明确不确定性与信息缺口。",
                depth_policy=DepthPolicy(min_sources=3, max_iterations=1, max_results=8),
            )
        )

    return sections, coverage
