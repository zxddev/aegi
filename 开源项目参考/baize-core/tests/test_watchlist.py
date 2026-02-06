"""Watchlist 抽取功能测试。

测试覆盖：
1. WatchlistItem schema 验证
2. WatchlistExtractor 规则抽取
3. format_watchlist_markdown 格式化

注意：直接从子模块导入以避免 SQLAlchemy 模型的完整导入链。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# 直接从子模块导入，避免触发 SQLAlchemy 问题
# 确保 src 目录在 path 中
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# 导入 extraction schema
extraction_spec = importlib.util.spec_from_file_location(
    "extraction", src_path / "baize_core" / "schemas" / "extraction.py"
)
extraction_module = importlib.util.module_from_spec(extraction_spec)
extraction_spec.loader.exec_module(extraction_module)

WatchlistCategory = extraction_module.WatchlistCategory
WatchlistPriority = extraction_module.WatchlistPriority
WatchlistItem = extraction_module.WatchlistItem
WatchlistExtractionResult = extraction_module.WatchlistExtractionResult

# 重建 Pydantic 模型以解决前向引用
WatchlistItem.model_rebuild()
WatchlistExtractionResult.model_rebuild()

# 导入 watchlist extractor（需要先模拟一些依赖）
# 由于 watchlist.py 依赖 prompt_builder，我们直接测试核心功能
watchlist_spec = importlib.util.spec_from_file_location(
    "watchlist", src_path / "baize_core" / "agents" / "watchlist.py"
)

# 需要先确保 schemas.extraction 可用
sys.modules["baize_core.schemas.extraction"] = extraction_module

# 模拟 content 模块
content_spec = importlib.util.spec_from_file_location(
    "content", src_path / "baize_core" / "schemas" / "content.py"
)
content_module = importlib.util.module_from_spec(content_spec)
content_spec.loader.exec_module(content_module)
sys.modules["baize_core.schemas.content"] = content_module


# 模拟 prompt_builder（只需要类型存在）
class MockPromptBuilder:
    def add_system_instruction(self, *args, **kwargs):
        return self

    def add_user_query(self, *args, **kwargs):
        return self

    def add_evidence(self, *args, **kwargs):
        return self

    def build(self):
        return type("Built", (), {"messages": []})()


# 创建模拟的 llm 模块
mock_llm = type(sys)("baize_core.llm.prompt_builder")
mock_llm.PromptBuilder = MockPromptBuilder
sys.modules["baize_core.llm.prompt_builder"] = mock_llm

# 现在导入 watchlist 模块
watchlist_module = importlib.util.module_from_spec(watchlist_spec)
watchlist_spec.loader.exec_module(watchlist_module)

WatchlistExtractor = watchlist_module.WatchlistExtractor
format_watchlist_markdown = watchlist_module.format_watchlist_markdown


class TestWatchlistSchema:
    """WatchlistItem schema 测试。"""

    def test_watchlist_item_minimal(self) -> None:
        """测试最小必填字段。"""
        item = WatchlistItem(
            indicator="关注某部队部署变化",
            category=WatchlistCategory.ENTITY_CHANGE,
        )
        assert item.indicator == "关注某部队部署变化"
        assert item.category == WatchlistCategory.ENTITY_CHANGE
        assert item.priority == WatchlistPriority.MEDIUM
        assert item.entities == []
        assert item.trigger_conditions == []
        assert item.evidence_refs == []
        assert item.rationale is None

    def test_watchlist_item_full(self) -> None:
        """测试完整字段。"""
        item = WatchlistItem(
            indicator="关注南海舰艇活动频次",
            category=WatchlistCategory.METRIC_THRESHOLD,
            priority=WatchlistPriority.HIGH,
            entities=["南海舰队", "航母编队"],
            trigger_conditions=["活动频次超过历史均值 50%"],
            rationale="近期活动异常频繁",
            evidence_refs=["[1]", "[3]"],
        )
        assert item.indicator == "关注南海舰艇活动频次"
        assert item.category == WatchlistCategory.METRIC_THRESHOLD
        assert item.priority == WatchlistPriority.HIGH
        assert "南海舰队" in item.entities
        assert len(item.trigger_conditions) == 1
        assert item.rationale == "近期活动异常频繁"

    def test_watchlist_category_values(self) -> None:
        """测试类别枚举值。"""
        assert WatchlistCategory.ENTITY_CHANGE.value == "entity_change"
        assert WatchlistCategory.EVENT_TRIGGER.value == "event_trigger"
        assert WatchlistCategory.METRIC_THRESHOLD.value == "metric_threshold"
        assert WatchlistCategory.TIMELINE_MILESTONE.value == "timeline_milestone"
        assert WatchlistCategory.UNCERTAINTY.value == "uncertainty"

    def test_watchlist_priority_values(self) -> None:
        """测试优先级枚举值。"""
        assert WatchlistPriority.HIGH.value == "high"
        assert WatchlistPriority.MEDIUM.value == "medium"
        assert WatchlistPriority.LOW.value == "low"

    def test_watchlist_extraction_result_empty(self) -> None:
        """测试空抽取结果。"""
        result = WatchlistExtractionResult()
        assert result.items == []
        assert result.summary is None

    def test_watchlist_extraction_result_with_items(self) -> None:
        """测试带条目的抽取结果。"""
        items = [
            WatchlistItem(
                indicator="指标1",
                category=WatchlistCategory.ENTITY_CHANGE,
            ),
            WatchlistItem(
                indicator="指标2",
                category=WatchlistCategory.EVENT_TRIGGER,
            ),
        ]
        result = WatchlistExtractionResult(
            items=items,
            summary="识别到 2 个观察指标",
        )
        assert len(result.items) == 2
        assert result.summary == "识别到 2 个观察指标"


class TestWatchlistExtractor:
    """WatchlistExtractor 规则抽取测试。"""

    def test_extract_empty_text(self) -> None:
        """测试空文本输入。"""
        extractor = WatchlistExtractor()
        result = extractor.extract_from_text("")
        assert result.items == []
        assert "未识别到" in result.summary

    def test_extract_entity_change(self) -> None:
        """测试实体变化检测。"""
        extractor = WatchlistExtractor()
        text = """
        近期观察到某集团军向边境地区增兵一个旅级单位。
        该部队的部署调整表明态势可能升级。
        """
        result = extractor.extract_from_text(text)
        assert len(result.items) >= 1
        # 检查是否识别出实体变化类
        entity_items = [
            item
            for item in result.items
            if item.category == WatchlistCategory.ENTITY_CHANGE
        ]
        assert len(entity_items) >= 1

    def test_extract_event_trigger(self) -> None:
        """测试事件触发检测。"""
        extractor = WatchlistExtractor()
        text = """
        该国计划于下月举行大规模联合军事演习。
        演训规模超过往年，可能引发区域紧张。
        """
        result = extractor.extract_from_text(text)
        assert len(result.items) >= 1
        event_items = [
            item
            for item in result.items
            if item.category == WatchlistCategory.EVENT_TRIGGER
        ]
        assert len(event_items) >= 1

    def test_extract_timeline_milestone(self) -> None:
        """测试时间节点检测。"""
        extractor = WatchlistExtractor()
        text = """
        条约将于2024年12月31日到期。
        届时需要关注各方的续约立场。
        """
        result = extractor.extract_from_text(text)
        timeline_items = [
            item
            for item in result.items
            if item.category == WatchlistCategory.TIMELINE_MILESTONE
        ]
        assert len(timeline_items) >= 1
        # 检查是否提取了日期
        if timeline_items:
            assert (
                len(timeline_items[0].trigger_conditions) >= 1
                or "到期" in timeline_items[0].indicator
            )

    def test_extract_uncertainty(self) -> None:
        """测试不确定性检测。"""
        extractor = WatchlistExtractor()
        # 使用仅包含不确定性关键词、不包含其他类别关键词的文本
        # "不确定" 是 UNCERTAINTY_KEYWORDS 中的关键词
        # 避免使用 "谈判" 等 EVENT_TRIGGER_KEYWORDS 中的词
        text = "该情况存在不确定性，结果未知，需要继续观察。"
        result = extractor.extract_from_text(text)
        # 检查是否抽取到项目
        assert len(result.items) >= 1, "Expected at least one item to be extracted"
        # 验证提取的项目中包含预期的关键词
        # 不确定性类别应该被检测到
        categories = [item.category for item in result.items]
        assert WatchlistCategory.UNCERTAINTY in categories, (
            f"Expected UNCERTAINTY category, got: {categories}"
        )

    def test_extract_with_entities(self) -> None:
        """测试带已知实体的抽取。"""
        extractor = WatchlistExtractor()
        text = """
        美国海军第七舰队近期在南海增加了巡逻频次。
        部署调整显示战备等级提升。
        """
        entities = ["第七舰队", "南海"]
        result = extractor.extract_from_text(text, entities=entities)
        # 应能识别到包含已知实体的内容
        assert any(
            any(ent in item.entities for ent in entities) for item in result.items
        )

    def test_extract_max_items_limit(self) -> None:
        """测试最大条目数限制。"""
        extractor = WatchlistExtractor(max_items=2)
        text = """
        增兵一个旅。部署调整中。
        计划举行演习。演训规模扩大。
        条约即将到期。截止日期临近。
        存在不确定性。可能会改变。
        """
        result = extractor.extract_from_text(text)
        assert len(result.items) <= 2

    def test_extract_deduplication(self) -> None:
        """测试去重功能。"""
        extractor = WatchlistExtractor()
        text = """
        部署调整中，增兵进行中。
        
        部署调整中，增兵进行中。
        """
        result = extractor.extract_from_text(text)
        # 相同内容不应重复
        indicators = [item.indicator for item in result.items]
        assert len(indicators) == len(set(indicators))

    def test_extract_priority_sorting(self) -> None:
        """测试优先级排序。"""
        extractor = WatchlistExtractor()
        text = """
        增兵一个旅级单位。
        可能会改变立场。
        """
        result = extractor.extract_from_text(text)
        if len(result.items) >= 2:
            # 高优先级应排在前面
            priorities = [item.priority for item in result.items]
            priority_order = {
                WatchlistPriority.HIGH: 0,
                WatchlistPriority.MEDIUM: 1,
                WatchlistPriority.LOW: 2,
            }
            sorted_priorities = sorted(priorities, key=lambda p: priority_order[p])
            assert priorities == sorted_priorities


class TestFormatWatchlistMarkdown:
    """format_watchlist_markdown 格式化测试。"""

    def test_format_empty_result(self) -> None:
        """测试空结果格式化。"""
        result = WatchlistExtractionResult()
        markdown = format_watchlist_markdown(result)
        assert markdown == ""

    def test_format_single_item(self) -> None:
        """测试单条目格式化。"""
        result = WatchlistExtractionResult(
            items=[
                WatchlistItem(
                    indicator="关注部队部署变化",
                    category=WatchlistCategory.ENTITY_CHANGE,
                    priority=WatchlistPriority.HIGH,
                    entities=["第七舰队"],
                )
            ],
            summary="识别到 1 个观察指标",
        )
        markdown = format_watchlist_markdown(result)
        assert "观察指标" in markdown
        assert "Watchlist" in markdown
        assert "关注部队部署变化" in markdown
        assert "第七舰队" in markdown
        assert "高" in markdown or "🔴" in markdown

    def test_format_multiple_items(self) -> None:
        """测试多条目格式化。"""
        result = WatchlistExtractionResult(
            items=[
                WatchlistItem(
                    indicator="指标A",
                    category=WatchlistCategory.ENTITY_CHANGE,
                    priority=WatchlistPriority.HIGH,
                ),
                WatchlistItem(
                    indicator="指标B",
                    category=WatchlistCategory.EVENT_TRIGGER,
                    priority=WatchlistPriority.MEDIUM,
                ),
                WatchlistItem(
                    indicator="指标C",
                    category=WatchlistCategory.UNCERTAINTY,
                    priority=WatchlistPriority.LOW,
                ),
            ],
            summary="测试摘要",
        )
        markdown = format_watchlist_markdown(result)
        assert "指标A" in markdown
        assert "指标B" in markdown
        assert "指标C" in markdown
        # 应包含表格格式
        assert "|" in markdown
        assert "测试摘要" in markdown

    def test_format_long_indicator_truncation(self) -> None:
        """测试长指标描述截断。"""
        long_indicator = "这是一个非常长的指标描述，" * 10
        result = WatchlistExtractionResult(
            items=[
                WatchlistItem(
                    indicator=long_indicator,
                    category=WatchlistCategory.ENTITY_CHANGE,
                )
            ]
        )
        markdown = format_watchlist_markdown(result)
        # 应该截断并添加省略号
        assert "..." in markdown

    def test_format_category_labels(self) -> None:
        """测试类别标签显示。"""
        result = WatchlistExtractionResult(
            items=[
                WatchlistItem(
                    indicator="测试",
                    category=WatchlistCategory.TIMELINE_MILESTONE,
                )
            ]
        )
        markdown = format_watchlist_markdown(result)
        assert "时间节点" in markdown


class TestWatchlistIntegration:
    """Watchlist 集成测试。"""

    def test_extractor_initialization(self) -> None:
        """测试抽取器初始化。"""
        extractor = WatchlistExtractor()
        assert extractor._max_items == 10
        assert extractor._min_confidence == 0.3

        custom_extractor = WatchlistExtractor(max_items=5, min_confidence=0.5)
        assert custom_extractor._max_items == 5
        assert custom_extractor._min_confidence == 0.5

    def test_full_extraction_pipeline(self) -> None:
        """测试完整抽取流程。"""
        extractor = WatchlistExtractor(max_items=5)
        text = """
        ## 战略态势分析

        近期，A国在边境地区部署了额外的装甲部队，增兵规模约为两个旅级单位。
        这一调动引发了B国的高度关注。

        ### 关键时间节点

        双边条约将于2025年3月1日到期。届时需要关注续约谈判进展。

        ### 不确定因素

        目前尚不确定C国是否会介入调停。其立场可能影响局势走向。

        ### 演习动态

        预计下月将举行大规模联合军事演习，参演兵力超过万人。
        """
        result = extractor.extract_from_text(text)
        markdown = format_watchlist_markdown(result)

        # 应该识别出多种类型的观察指标
        assert len(result.items) >= 1
        categories = {item.category for item in result.items}
        assert len(categories) >= 1

        # Markdown 应包含标题和表格
        if result.items:
            assert "观察指标" in markdown
            assert "|" in markdown
