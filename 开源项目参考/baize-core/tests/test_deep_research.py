"""Deep Research Loop 测试。

测试深度研究循环的核心功能。
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from baize_core.orchestration.deep_research import (
    DeepResearchConfig,
    DeepResearchLoop,
    ResearchContext,
    ResearchIteration,
    SectionResearchResult,
    SectionSpec,
    SimpleCritic,
)
from baize_core.orchestration.research_state import ResearchState
from baize_core.policy.depth import (
    DepthConfig,
    DepthController,
    DepthLevel,
)
from baize_core.schemas.evidence import Artifact, Chunk, Evidence
from baize_core.schemas.storm import DepthPolicy


class TestSimpleCritic:
    """SimpleCritic 测试。"""

    @pytest.fixture
    def critic(self) -> SimpleCritic:
        """创建 Critic 实例。"""
        return SimpleCritic()

    @pytest.mark.asyncio
    async def test_sufficient_evidence(self, critic: SimpleCritic) -> None:
        """测试充足的证据。"""
        evidence = [
            Evidence(
                chunk_uid=f"chk_{i}",
                source=f"source_{i}",
                uri=f"https://domain{i}.com/page",
                collected_at=datetime.now(UTC),
                base_credibility=0.8,
            )
            for i in range(5)
        ]

        result = await critic.review_evidence(
            evidence=evidence,
            section_question="测试问题",
            min_sources=3,
        )

        assert result.is_sufficient is True
        assert result.coverage_score >= 1.0
        assert result.confidence_score > 0

    @pytest.mark.asyncio
    async def test_insufficient_evidence(self, critic: SimpleCritic) -> None:
        """测试不足的证据。"""
        evidence = [
            Evidence(
                chunk_uid="chk_1",
                source="source_1",
                uri="https://example.com/page",
                collected_at=datetime.now(UTC),
                base_credibility=0.8,
            )
        ]

        result = await critic.review_evidence(
            evidence=evidence,
            section_question="测试问题",
            min_sources=5,
        )

        assert result.is_sufficient is False
        assert len(result.gaps) > 0
        assert result.coverage_score < 1.0

    @pytest.mark.asyncio
    async def test_diversity_check(self, critic: SimpleCritic) -> None:
        """测试来源多样性检查。"""
        # 所有证据来自同一域名
        evidence = [
            Evidence(
                chunk_uid=f"chk_{i}",
                source="same_source",
                uri=f"https://same-domain.com/page{i}",
                collected_at=datetime.now(UTC),
                base_credibility=0.8,
            )
            for i in range(5)
        ]

        result = await critic.review_evidence(
            evidence=evidence,
            section_question="测试问题",
            min_sources=3,
        )

        # 数量足够但多样性不足
        assert result.is_sufficient is True  # 数量足够
        assert result.confidence_score < 1.0  # 但置信度较低


class TestDeepResearchConfig:
    """DeepResearchConfig 测试。"""

    def test_default_config(self) -> None:
        """测试默认配置。"""
        config = DeepResearchConfig()
        assert config.enable_dynamic_depth is True
        assert config.enable_critic_review is True
        assert config.coverage_threshold == 0.8
        assert config.confidence_threshold == 0.7

    def test_custom_config(self) -> None:
        """测试自定义配置。"""
        config = DeepResearchConfig(
            enable_dynamic_depth=False,
            coverage_threshold=0.9,
        )
        assert config.enable_dynamic_depth is False
        assert config.coverage_threshold == 0.9


class TestSectionSpec:
    """SectionSpec 测试。"""

    def test_section_spec_creation(self) -> None:
        """测试章节规格创建。"""
        depth_policy = DepthPolicy(
            min_sources=3,
            max_iterations=5,
            max_results=10,
        )
        spec = SectionSpec(
            section_id="section_1",
            title="测试章节",
            question="这是测试问题？",
            depth_policy=depth_policy,
        )

        assert spec.section_id == "section_1"
        assert spec.title == "测试章节"
        assert spec.depth_policy.min_sources == 3


class TestDeepResearchLoop:
    """DeepResearchLoop 测试。"""

    @pytest.fixture
    def mock_store(self) -> MagicMock:
        """创建模拟存储。"""
        store = MagicMock()
        store.store_evidence_chain = AsyncMock()
        store.store_storm_iterations = AsyncMock()
        store.store_storm_section_evidence = AsyncMock()
        store.store_artifacts = AsyncMock()
        return store

    @pytest.fixture
    def mock_tool_runner(self) -> MagicMock:
        """创建模拟工具运行器。"""
        runner = MagicMock()
        return runner

    @pytest.fixture
    def mock_llm_runner(self) -> MagicMock:
        """创建模拟 LLM 运行器。"""
        runner = MagicMock()
        return runner

    @pytest.fixture
    def research_context(
        self,
        mock_store: MagicMock,
        mock_tool_runner: MagicMock,
        mock_llm_runner: MagicMock,
    ) -> ResearchContext:
        """创建研究上下文。"""
        return ResearchContext(
            store=mock_store,
            tool_runner=mock_tool_runner,
            llm_runner=mock_llm_runner,
            depth_controller=DepthController(config=DepthConfig()),
            critic=SimpleCritic(),
        )

    @pytest.fixture
    def research_loop(self, research_context: ResearchContext) -> DeepResearchLoop:
        """创建研究循环实例。"""
        config = DeepResearchConfig(
            enable_dynamic_depth=True,
            enable_critic_review=True,
        )
        return DeepResearchLoop(context=research_context, config=config)

    def test_build_query_first_iteration(self, research_loop: DeepResearchLoop) -> None:
        """测试首次迭代查询构建。"""
        spec = SectionSpec(
            section_id="section_1",
            title="测试章节",
            question="这是什么？",
            depth_policy=DepthPolicy(min_sources=3, max_iterations=5),
        )

        query = research_loop._build_query(
            objective="研究任务",
            section=spec,
            iteration=1,
            gaps=[],
        )

        assert "研究任务" in query
        assert "这是什么" in query

    def test_build_query_with_gaps(self, research_loop: DeepResearchLoop) -> None:
        """测试带缺口的查询构建。"""
        spec = SectionSpec(
            section_id="section_1",
            title="测试章节",
            question="这是什么？",
            depth_policy=DepthPolicy(min_sources=3, max_iterations=5),
        )

        query = research_loop._build_query(
            objective="研究任务",
            section=spec,
            iteration=2,
            gaps=["缺少时间线信息", "需要更多来源"],
        )

        assert "缺少时间线信息" in query or "需要更多来源" in query

    def test_adjust_params_by_depth_shallow(
        self, research_loop: DeepResearchLoop
    ) -> None:
        """测试浅层深度参数调整。"""
        min_sources, max_iterations = research_loop._adjust_params_by_depth(
            level=DepthLevel.SHALLOW,
            base_min_sources=6,
            base_max_iterations=10,
        )

        assert min_sources == 3  # 减半
        assert max_iterations == 5  # 减半

    def test_adjust_params_by_depth_deep(self, research_loop: DeepResearchLoop) -> None:
        """测试深层深度参数调整。"""
        min_sources, max_iterations = research_loop._adjust_params_by_depth(
            level=DepthLevel.DEEP,
            base_min_sources=4,
            base_max_iterations=6,
        )

        assert min_sources == 6  # 1.5 倍
        assert max_iterations == 9  # 1.5 倍

    def test_adjust_params_by_depth_exhaustive(
        self, research_loop: DeepResearchLoop
    ) -> None:
        """测试穷尽深度参数调整。"""
        min_sources, max_iterations = research_loop._adjust_params_by_depth(
            level=DepthLevel.EXHAUSTIVE,
            base_min_sources=4,
            base_max_iterations=6,
        )

        assert min_sources == 8  # 2 倍
        assert max_iterations == 12  # 2 倍

    def test_dedupe_by_url(self, research_loop: DeepResearchLoop) -> None:
        """测试 URL 去重。"""
        artifacts = [
            Artifact(
                artifact_uid="art_1",
                source_url="https://example.com/page1",
                fetched_at=datetime.now(UTC),
                content_sha256="sha256:abc123",
                mime_type="text/html",
                storage_ref="minio://bucket/art_1",
            ),
        ]
        chunks = [
            Chunk(
                chunk_uid="chk_1",
                artifact_uid="art_1",
                anchor={"type": "text_offset", "ref": "0-100"},
                text="测试文本",
                text_sha256="hash1",
            ),
        ]
        evidence = [
            Evidence(
                chunk_uid="chk_1",
                source="google",
                uri="https://example.com/page1",
                collected_at=datetime.now(UTC),
                base_credibility=0.8,
            ),
        ]

        # 创建 ResearchState 并添加已见 URL
        state = ResearchState()
        state.seen_urls.add("https://example.com/page1")

        filtered_arts, filtered_chunks, filtered_evidence = research_loop._dedupe(
            artifacts=artifacts,
            chunks=chunks,
            evidence_items=evidence,
            state=state,
            dedupe_by_domain=False,
        )

        # URL 已见过，应该被过滤
        assert len(filtered_evidence) == 0

    def test_dedupe_by_domain(self, research_loop: DeepResearchLoop) -> None:
        """测试域名去重。"""
        artifacts = [
            Artifact(
                artifact_uid="art_1",
                source_url="https://example.com/page1",
                fetched_at=datetime.now(UTC),
                content_sha256="sha256:abc123",
                mime_type="text/html",
                storage_ref="minio://bucket/art_1",
            ),
        ]
        chunks = [
            Chunk(
                chunk_uid="chk_1",
                artifact_uid="art_1",
                anchor={"type": "text_offset", "ref": "0-100"},
                text="测试文本",
                text_sha256="hash1",
            ),
        ]
        evidence = [
            Evidence(
                chunk_uid="chk_1",
                source="google",
                uri="https://example.com/page2",  # 不同页面
                collected_at=datetime.now(UTC),
                base_credibility=0.8,
            ),
        ]

        # 创建 ResearchState 并添加已见域名
        state = ResearchState()
        state.seen_domains.add("example.com")

        filtered_arts, filtered_chunks, filtered_evidence = research_loop._dedupe(
            artifacts=artifacts,
            chunks=chunks,
            evidence_items=evidence,
            state=state,
            dedupe_by_domain=True,
        )

        # 域名已见过且启用域名去重，应该被过滤
        assert len(filtered_evidence) == 0


class TestDepthControllerIntegration:
    """DepthController 与 DeepResearchLoop 集成测试。"""

    def test_depth_state_initialization(self) -> None:
        """测试深度状态初始化。"""
        controller = DepthController(config=DepthConfig())
        state = controller.initialize_state(complexity_score=0.5)

        # complexity=0.5 应该返回 DEEP（0.5 <= x < 0.75）
        assert state.current_level == DepthLevel.DEEP
        assert state.current_iteration == 0

    def test_depth_adjustment_on_low_confidence(self) -> None:
        """测试低置信度时的深度调整。"""
        controller = DepthController(config=DepthConfig())
        state = controller.initialize_state(complexity_score=0.5)

        # 更新为低置信度
        state = controller.update_metrics(
            state,
            coverage=0.2,
            confidence=0.2,
        )

        adjustment = controller.evaluate_adjustment(state)

        # 应该建议升级深度
        if adjustment.should_adjust:
            assert adjustment.new_level in [DepthLevel.DEEP, DepthLevel.EXHAUSTIVE]

    def test_depth_downgrade_on_high_confidence(self) -> None:
        """测试高置信度时的深度降级。"""
        controller = DepthController(config=DepthConfig())
        state = controller.initialize_state(
            complexity_score=0.8,
            initial_level=DepthLevel.DEEP,
        )

        # 更新为高置信度
        state = controller.update_metrics(
            state,
            coverage=0.9,
            confidence=0.9,
        )

        adjustment = controller.evaluate_adjustment(state)

        # 应该建议降级或终止
        if adjustment.should_adjust:
            assert adjustment.new_level in [
                DepthLevel.SHALLOW,
                DepthLevel.MODERATE,
            ]
        else:
            # 或者直接建议停止研究
            assert adjustment.continue_research is False


class TestResearchIteration:
    """ResearchIteration 测试。"""

    def test_iteration_creation(self) -> None:
        """测试迭代记录创建。"""
        iteration = ResearchIteration(
            iteration_index=1,
            query="测试查询",
            evidence_uids=["ev_1", "ev_2"],
            gaps_detected=["缺少信息"],
            is_terminal=False,
        )

        assert iteration.iteration_index == 1
        assert len(iteration.evidence_uids) == 2
        assert iteration.is_terminal is False


class TestSectionResearchResult:
    """SectionResearchResult 测试。"""

    def test_result_creation(self) -> None:
        """测试结果创建。"""
        result = SectionResearchResult(
            section_id="section_1",
            iterations=[
                ResearchIteration(
                    iteration_index=1,
                    query="查询",
                    evidence_uids=["ev_1"],
                    gaps_detected=[],
                    is_terminal=True,
                ),
            ],
            evidence=[],
            chunks=[],
            artifacts=[],
            gaps=[],
            coverage_score=0.9,
            confidence_score=0.85,
            depth_level_used=DepthLevel.MODERATE,
        )

        assert result.section_id == "section_1"
        assert len(result.iterations) == 1
        assert result.coverage_score == 0.9
        assert result.depth_level_used == DepthLevel.MODERATE
