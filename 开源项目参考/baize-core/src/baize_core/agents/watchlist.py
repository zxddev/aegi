"""Watchlist 抽取器。

从报告内容中抽取观察指标（Watchlist），用于后续态势追踪。
观察指标包括需要持续关注的实体变化、事件触发条件、指标阈值等。

支持两种模式：
1. 规则驱动（默认）：基于关键词和模式匹配
2. LLM 驱动：使用结构化输出生成抽取结果
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from baize_core.llm.prompt_builder import PromptBuilder
from baize_core.schemas.content import ContentSource
from baize_core.schemas.extraction import (
    WatchlistCategory,
    WatchlistExtractionResult,
    WatchlistItem,
    WatchlistPriority,
)

if TYPE_CHECKING:
    from baize_core.llm.runner import LlmRunner
    from baize_core.schemas.policy import StageType


# LLM 抽取系统提示
WATCHLIST_SYSTEM_PROMPT = """你是一个军事情报分析专家，负责从研究报告中抽取观察指标（Watchlist）。

观察指标是需要持续关注的态势信号，用于预警和追踪。

## 观察指标类别

1. **实体变化（entity_change）**：部署调整、能力变化、状态转换
   - 例如：关注某部队是否继续向边境增兵
   
2. **事件触发条件（event_trigger）**：可能引发态势变化的事件信号
   - 例如：关注是否有新的军事演习公告
   
3. **指标阈值（metric_threshold）**：需要监控的数值指标及其临界值
   - 例如：关注某海域舰艇活动频次是否超过历史均值
   
4. **时间节点（timeline_milestone）**：关键日期或时间窗口
   - 例如：关注某条约到期日前后的行动
   
5. **不确定性消解（uncertainty）**：需要进一步确认或澄清的信息
   - 例如：关注某国对事件的官方回应

## 输出要求

- 每个指标必须明确、可操作
- 指出关联的实体名称
- 说明触发条件（如果适用）
- 给出优先级（high/medium/low）
- 提供列入观察的理由
"""


# 关键词模式（用于规则驱动抽取）
ENTITY_CHANGE_KEYWORDS = [
    "部署",
    "增兵",
    "撤离",
    "调动",
    "编制变化",
    "能力提升",
    "装备更新",
    "基地建设",
    "战备状态",
    "alert",
    "deploy",
    "reinforce",
]

EVENT_TRIGGER_KEYWORDS = [
    "演习",
    "演训",
    "冲突",
    "对峙",
    "升级",
    "谈判",
    "协议",
    "制裁",
    "声明",
    "exercise",
    "tension",
    "escalation",
]

TIMELINE_KEYWORDS = [
    "到期",
    "截止",
    "窗口",
    "周年",
    "纪念日",
    "选举",
    "峰会",
    "会议",
    "deadline",
    "anniversary",
]

UNCERTAINTY_KEYWORDS = [
    "不确定",
    "未知",
    "存疑",
    "待确认",
    "可能",
    "或",
    "unclear",
    "uncertain",
    "unconfirmed",
]


class WatchlistExtractor:
    """Watchlist 抽取器。

    职责：
    1. 从报告内容中识别观察指标
    2. 分类和优先级排序
    3. 关联实体和触发条件
    """

    def __init__(
        self,
        *,
        max_items: int = 10,
        min_confidence: float = 0.3,
    ) -> None:
        """初始化抽取器。

        Args:
            max_items: 最大抽取数量
            min_confidence: 最低置信度阈值（用于过滤低质量抽取）
        """
        self._max_items = max_items
        self._min_confidence = min_confidence

    def extract_from_text(
        self,
        text: str,
        *,
        entities: Sequence[str] | None = None,
    ) -> WatchlistExtractionResult:
        """使用规则从文本中抽取观察指标（规则驱动模式）。

        基于关键词和模式匹配进行抽取，适用于简单场景。

        Args:
            text: 报告文本内容
            entities: 已知实体列表（用于关联）

        Returns:
            WatchlistExtractionResult 抽取结果
        """
        items: list[WatchlistItem] = []
        known_entities = set(entities or [])

        # 按段落分析
        paragraphs = text.split("\n\n")
        for para in paragraphs:
            para_items = self._extract_from_paragraph(para, known_entities)
            items.extend(para_items)

        # 去重和排序
        items = self._dedupe_and_sort(items)

        # 限制数量
        items = items[: self._max_items]

        # 生成摘要
        summary = self._generate_summary(items)

        return WatchlistExtractionResult(
            items=items,
            summary=summary,
        )

    def _extract_from_paragraph(
        self,
        para: str,
        known_entities: set[str],
    ) -> list[WatchlistItem]:
        """从单个段落中抽取观察指标。

        Args:
            para: 段落文本
            known_entities: 已知实体集合

        Returns:
            抽取的指标列表
        """
        items: list[WatchlistItem] = []
        para_lower = para.lower()

        # 检测实体变化
        if any(kw in para_lower or kw in para for kw in ENTITY_CHANGE_KEYWORDS):
            entities = self._find_entities_in_text(para, known_entities)
            if entities or "部署" in para or "调动" in para:
                items.append(
                    WatchlistItem(
                        indicator=self._extract_indicator_text(para, "实体变化"),
                        category=WatchlistCategory.ENTITY_CHANGE,
                        priority=WatchlistPriority.HIGH,
                        entities=entities,
                        rationale="检测到部署或能力变化相关描述",
                    )
                )

        # 检测事件触发
        if any(kw in para_lower or kw in para for kw in EVENT_TRIGGER_KEYWORDS):
            entities = self._find_entities_in_text(para, known_entities)
            items.append(
                WatchlistItem(
                    indicator=self._extract_indicator_text(para, "事件触发"),
                    category=WatchlistCategory.EVENT_TRIGGER,
                    priority=WatchlistPriority.MEDIUM,
                    entities=entities,
                    rationale="检测到潜在触发事件描述",
                )
            )

        # 检测时间节点
        if any(kw in para_lower or kw in para for kw in TIMELINE_KEYWORDS):
            # 尝试提取日期
            dates = self._extract_dates(para)
            items.append(
                WatchlistItem(
                    indicator=self._extract_indicator_text(para, "时间节点"),
                    category=WatchlistCategory.TIMELINE_MILESTONE,
                    priority=WatchlistPriority.MEDIUM,
                    trigger_conditions=dates,
                    rationale="检测到关键时间节点",
                )
            )

        # 检测不确定性
        if any(kw in para_lower or kw in para for kw in UNCERTAINTY_KEYWORDS):
            items.append(
                WatchlistItem(
                    indicator=self._extract_indicator_text(para, "待确认信息"),
                    category=WatchlistCategory.UNCERTAINTY,
                    priority=WatchlistPriority.LOW,
                    rationale="检测到不确定性描述",
                )
            )

        return items

    def _find_entities_in_text(
        self,
        text: str,
        known_entities: set[str],
    ) -> list[str]:
        """在文本中查找已知实体。

        Args:
            text: 文本内容
            known_entities: 已知实体集合

        Returns:
            找到的实体列表
        """
        found = []
        for entity in known_entities:
            if entity in text:
                found.append(entity)
        return found[:5]  # 最多返回 5 个

    def _extract_indicator_text(self, para: str, fallback: str) -> str:
        """从段落中提取指标描述文本。

        Args:
            para: 段落文本
            fallback: 回退描述

        Returns:
            指标描述
        """
        # 取段落的第一句话作为指标描述
        sentences = re.split(r"[。.!！?？]", para)
        if sentences and sentences[0].strip():
            indicator = sentences[0].strip()[:100]
            return f"关注：{indicator}"
        return f"关注：{fallback}"

    def _extract_dates(self, text: str) -> list[str]:
        """从文本中提取日期。

        Args:
            text: 文本内容

        Returns:
            提取的日期列表
        """
        # 匹配常见日期格式
        patterns = [
            r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?",  # 2024-01-15, 2024年1月15日
            r"\d{1,2}月\d{1,2}日",  # 1月15日
        ]
        dates = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            dates.extend(matches)
        return dates[:3]  # 最多返回 3 个

    def _dedupe_and_sort(
        self,
        items: list[WatchlistItem],
    ) -> list[WatchlistItem]:
        """去重并按优先级排序。

        Args:
            items: 原始指标列表

        Returns:
            处理后的列表
        """
        # 按 indicator 去重
        seen: set[str] = set()
        unique_items: list[WatchlistItem] = []
        for item in items:
            key = item.indicator[:50]
            if key not in seen:
                seen.add(key)
                unique_items.append(item)

        # 按优先级排序
        priority_order = {
            WatchlistPriority.HIGH: 0,
            WatchlistPriority.MEDIUM: 1,
            WatchlistPriority.LOW: 2,
        }
        unique_items.sort(key=lambda x: priority_order.get(x.priority, 99))

        return unique_items

    def _generate_summary(self, items: list[WatchlistItem]) -> str:
        """生成观察指标摘要。

        Args:
            items: 指标列表

        Returns:
            摘要文本
        """
        if not items:
            return "未识别到需要持续关注的观察指标。"

        category_counts: dict[WatchlistCategory, int] = {}
        for item in items:
            category_counts[item.category] = category_counts.get(item.category, 0) + 1

        high_priority_count = sum(
            1 for item in items if item.priority == WatchlistPriority.HIGH
        )

        parts = [f"识别到 {len(items)} 个观察指标"]
        if high_priority_count:
            parts.append(f"其中 {high_priority_count} 个为高优先级")

        return "，".join(parts) + "。"

    async def extract_with_llm(
        self,
        text: str,
        *,
        llm_runner: LlmRunner,
        stage: StageType,
        task_id: str,
        section_id: str | None = None,
    ) -> WatchlistExtractionResult:
        """使用 LLM 抽取观察指标（LLM 驱动模式）。

        通过结构化输出约束 LLM 生成标准化的抽取结果。

        Args:
            text: 报告文本内容
            llm_runner: LLM 运行器
            stage: 编排阶段
            task_id: 任务 ID
            section_id: 章节 ID（可选）

        Returns:
            WatchlistExtractionResult 结构化抽取结果
        """
        from baize_core.llm.structured import GenerationMode

        # 构建抽取提示
        user_query = (
            "请从以下报告内容中抽取观察指标（Watchlist）。\n\n"
            "要求：\n"
            f"1. 最多抽取 {self._max_items} 个最重要的指标\n"
            "2. 每个指标必须明确、可操作\n"
            "3. 按优先级排序（high > medium > low）\n"
            "4. 关联相关实体\n"
            "5. 说明列入观察的理由\n"
        )
        prompt = (
            PromptBuilder()
            .add_system_instruction(
                WATCHLIST_SYSTEM_PROMPT,
                source_type=ContentSource.INTERNAL,
                source_ref="watchlist_system",
            )
            .add_user_query(
                user_query,
                source_type=ContentSource.INTERNAL,
                source_ref="watchlist_query",
            )
            .add_evidence(
                f"## 报告内容\n\n{text}",
                source_ref="watchlist_content",
                content_type="report_content",
            )
            .build()
        )
        system_msg = next(
            (m["content"] for m in prompt.messages if m["role"] == "system"), ""
        )
        user_msg = next(
            (m["content"] for m in prompt.messages if m["role"] == "user"), ""
        )

        result = await llm_runner.generate_structured(
            system=system_msg,
            user=user_msg,
            schema=WatchlistExtractionResult,
            stage=stage,
            task_id=task_id,
            section_id=section_id,
            max_retries=3,
            mode=GenerationMode.POST_VALIDATE,
        )

        return result.data


def format_watchlist_markdown(result: WatchlistExtractionResult) -> str:
    """将观察指标结果格式化为 Markdown。

    Args:
        result: 观察指标抽取结果

    Returns:
        Markdown 格式的文本
    """
    if not result.items:
        return ""

    lines = [
        "## 观察指标（Watchlist）",
        "",
        "以下指标需要持续关注，用于态势追踪和预警：",
        "",
    ]

    # 按类别分组
    category_labels = {
        WatchlistCategory.ENTITY_CHANGE: "实体变化",
        WatchlistCategory.EVENT_TRIGGER: "事件触发",
        WatchlistCategory.METRIC_THRESHOLD: "指标阈值",
        WatchlistCategory.TIMELINE_MILESTONE: "时间节点",
        WatchlistCategory.UNCERTAINTY: "待确认信息",
    }

    priority_labels = {
        WatchlistPriority.HIGH: "🔴 高",
        WatchlistPriority.MEDIUM: "🟡 中",
        WatchlistPriority.LOW: "🟢 低",
    }

    # 构建表格
    lines.append("| 优先级 | 类别 | 指标 | 关联实体 |")
    lines.append("|--------|------|------|----------|")

    for item in result.items:
        priority = priority_labels.get(item.priority, "中")
        category = category_labels.get(item.category, "其他")
        indicator = (
            item.indicator[:60] + "..." if len(item.indicator) > 60 else item.indicator
        )
        entities = ", ".join(item.entities[:3]) if item.entities else "-"
        lines.append(f"| {priority} | {category} | {indicator} | {entities} |")

    lines.append("")
    if result.summary:
        lines.append(f"*{result.summary}*")

    return "\n".join(lines)
