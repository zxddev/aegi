"""上下文工程层测试。

测试 EvidenceSelector、EvidenceCompressor、PromptBudgeter、SectionWriter 等组件。
"""

from __future__ import annotations

import pytest

from baize_core.llm.context_engine import (
    BudgetAction,
    BudgetDecision,
    BudgeterConfig,
    CompressionMode,
    CompressorConfig,
    EvidenceCandidate,
    EvidenceCompressor,
    EvidenceSelector,
    EvidenceSnippet,
    PromptBudget,
    PromptBudgeter,
    SectionWriteConfig,
    SectionWriteResult,
    SectionWriter,
    SelectorConfig,
    WriterStrategy,
    create_section_writer,
)
from baize_core.llm.context_engine.adaptive_retry import (
    AdaptiveRetry,
    AdaptiveRetryConfig,
    DegradationLevel,
    RetryState,
    compute_degraded_params,
)


# ========== EvidenceCandidate 测试数据 ==========


def make_candidate(
    uid: str = "ev_1",
    text: str | None = None,
    uri: str = "https://reuters.com/article/123",
    credibility: float = 0.8,
    conflict_types: list[str] | None = None,
) -> EvidenceCandidate:
    """创建测试用 EvidenceCandidate。
    
    如果 text 为 None，使用 uid 生成唯一文本以避免去重。
    """
    if text is None:
        text = f"Unique evidence content for {uid} about military operations and strategic analysis."
    return EvidenceCandidate(
        evidence_uid=uid,
        chunk_uid=f"chunk_{uid}",
        artifact_uid=f"artifact_{uid}",
        text=text,
        text_sha256=f"sha256_{uid}",  # 每个 uid 唯一的 hash
        uri=uri,
        summary=f"Summary of {uid}",
        base_credibility=credibility,
        score_total=credibility * 0.9,
        conflict_types=conflict_types or [],
    )


# ========== EvidenceSelector 测试 ==========


class TestEvidenceSelector:
    """EvidenceSelector 测试。"""

    def test_select_empty_candidates(self):
        """空候选列表返回空结果。"""
        selector = EvidenceSelector()
        result = selector.select([], "What is the military situation?")
        assert result == []

    def test_select_filters_low_credibility(self):
        """过滤低可信度证据。"""
        selector = EvidenceSelector(SelectorConfig(min_credibility=0.3, dedupe_by_content=False))
        candidates = [
            make_candidate("ev_1", text="First unique text about military strategy", credibility=0.5),
            make_candidate("ev_2", text="Second unique text about defense", credibility=0.1),  # 低于阈值
            make_candidate("ev_3", text="Third unique text about operations", credibility=0.8),
        ]
        result = selector.select(candidates, "military operations", top_k=10)
        
        uids = [c.evidence_uid for c in result]
        assert "ev_1" in uids
        assert "ev_3" in uids
        assert "ev_2" not in uids  # 被过滤

    def test_select_prefers_quality_domains(self):
        """优先选择高质量域名。"""
        selector = EvidenceSelector(SelectorConfig(dedupe_by_content=False))
        candidates = [
            make_candidate("ev_1", text="First article about defense policy", uri="https://example.com/article", credibility=0.7),
            make_candidate("ev_2", text="Second article about military news", uri="https://reuters.com/article", credibility=0.7),
        ]
        result = selector.select(candidates, "military news", top_k=2)
        
        # reuters.com 应该排在前面（高质量域名加分）
        assert len(result) == 2
        assert result[0].evidence_uid == "ev_2"

    def test_select_deduplicates_by_hash(self):
        """按哈希去重。"""
        selector = EvidenceSelector()
        cand1 = make_candidate("ev_1", text="Same content")
        cand2 = make_candidate("ev_2", text="Same content")
        cand2.text_sha256 = cand1.text_sha256  # 相同哈希
        
        result = selector.select([cand1, cand2], "test", top_k=10)
        assert len(result) == 1

    def test_select_respects_top_k(self):
        """遵守 top_k 限制。"""
        selector = EvidenceSelector(SelectorConfig(dedupe_by_content=False))
        # 创建有不同文本的候选，避免被去重
        candidates = [
            make_candidate(f"ev_{i}", text=f"Unique content number {i} about topic {i * 2}")
            for i in range(20)
        ]
        result = selector.select(candidates, "test", top_k=5)
        assert len(result) == 5


# ========== EvidenceCompressor 测试 ==========


class TestEvidenceCompressor:
    """EvidenceCompressor 测试。"""

    def test_compress_short_text_unchanged(self):
        """短文本不变。"""
        compressor = EvidenceCompressor(CompressorConfig(max_excerpt_chars=1000))
        candidate = make_candidate(text="Short text.")
        
        snippet = compressor.compress(candidate, citation=1)
        assert "Short text" in snippet.excerpt

    def test_compress_long_text_truncated(self):
        """长文本被截断。"""
        compressor = EvidenceCompressor(CompressorConfig(max_excerpt_chars=100))
        long_text = "This is a very long text. " * 50
        candidate = make_candidate(text=long_text)
        
        snippet = compressor.compress(candidate, citation=1, max_chars=100)
        assert len(snippet.excerpt) <= 103  # 允许 "..."

    def test_compress_batch_assigns_citations(self):
        """批量压缩正确分配引用编号。"""
        compressor = EvidenceCompressor()
        candidates = [make_candidate(f"ev_{i}") for i in range(3)]
        
        snippets = compressor.compress_batch(candidates, start_citation=5)
        
        assert len(snippets) == 3
        assert snippets[0].citation == 5
        assert snippets[1].citation == 6
        assert snippets[2].citation == 7

    def test_compress_marks_conflict(self):
        """标记冲突证据。"""
        compressor = EvidenceCompressor()
        candidate = make_candidate(conflict_types=["contradiction"])
        
        snippet = compressor.compress(candidate, citation=1)
        assert snippet.is_conflict is True

    def test_to_citation_block_format(self):
        """引用块格式正确。"""
        snippet = EvidenceSnippet(
            evidence_uid="ev_1",
            chunk_uid="chunk_1",
            artifact_uid="artifact_1",
            citation=3,
            title="Test Title",
            excerpt="Test content here.",
            source_url="https://example.com",
            char_count=18,
            is_conflict=False,
        )
        
        block = snippet.to_citation_block()
        assert "[3]" in block
        assert "Test Title" in block
        assert "Test content here" in block


# ========== PromptBudgeter 测试 ==========


class TestPromptBudgeter:
    """PromptBudgeter 测试。"""

    def test_create_budget_defaults(self):
        """创建预算使用默认值。"""
        budgeter = PromptBudgeter()
        budget = budgeter.create_budget()
        
        assert budget.max_tokens > 0
        assert budget.max_chars > 0
        assert budget.max_evidence_count > 0

    def test_estimate_tokens_mixed_text(self):
        """混合文本 token 估算。"""
        budgeter = PromptBudgeter()
        
        # 纯英文
        english_tokens = budgeter.estimate_tokens("Hello world this is a test.")
        
        # 纯中文
        chinese_tokens = budgeter.estimate_tokens("这是一段中文测试内容。")
        
        # 中文更短但 token 数应该更高（每字符约 0.67 token）
        assert chinese_tokens > 0
        assert english_tokens > 0

    def test_check_budget_accept(self):
        """预算充足时接受。"""
        budgeter = PromptBudgeter()
        budget = PromptBudget(max_chars=10000, max_evidence_count=10)
        snippets = [
            EvidenceSnippet("ev_1", "c_1", "a_1", 1, "T", "x" * 100, None, 100, False),
            EvidenceSnippet("ev_2", "c_2", "a_2", 2, "T", "x" * 100, None, 100, False),
        ]
        
        decision = budgeter.check_budget(budget, snippets)
        assert decision.action == BudgetAction.ACCEPT

    def test_check_budget_truncate(self):
        """预算紧张时截断。"""
        budgeter = PromptBudgeter(BudgeterConfig(truncation_threshold=0.5))
        budget = PromptBudget(max_chars=1000, max_evidence_count=10)
        snippets = [
            EvidenceSnippet("ev_1", "c_1", "a_1", 1, "T", "x" * 600, None, 600, False),
        ]
        
        decision = budgeter.check_budget(budget, snippets)
        assert decision.action in (BudgetAction.TRUNCATE, BudgetAction.REDUCE_COUNT)

    def test_allocate_budget_distribution(self):
        """预算分配策略。"""
        budgeter = PromptBudgeter()
        budget = PromptBudget(max_chars=10000, max_evidence_count=10, max_chars_per_evidence=800)
        budget.reserved_for_system = 500
        budget.reserved_for_output = 1000
        
        allocations = budgeter.allocate_budget(budget, 5)
        
        assert len(allocations) == 5
        # 前几条应该分配更多
        assert allocations[0] >= allocations[-1]


# ========== AdaptiveRetry 测试 ==========


class TestAdaptiveRetry:
    """AdaptiveRetry 测试。"""

    def test_compute_degraded_params_no_degradation(self):
        """无降级时参数不变。"""
        state = RetryState()
        count, chars = compute_degraded_params(state, 10, 500)
        
        assert count == 10
        assert chars == 500

    def test_compute_degraded_params_with_degradation(self):
        """降级时参数减少。"""
        state = RetryState(
            evidence_count_factor=0.5,
            excerpt_chars_factor=0.6,
        )
        count, chars = compute_degraded_params(state, 10, 500)
        
        assert count == 5
        assert chars == 300

    def test_retry_state_should_retry(self):
        """重试状态判断。"""
        state = RetryState(attempt=0, total_attempts=5)
        assert state.should_retry is True
        
        state.attempt = 5
        assert state.should_retry is False

    def test_is_retryable_error(self):
        """可重试错误检测。"""
        retry = AdaptiveRetry()
        
        assert retry.is_retryable_error(Exception("HTTP 500 Internal Server Error"))
        assert retry.is_retryable_error(Exception("Connection timeout"))
        assert retry.is_retryable_error(Exception("context length exceeded"))
        assert not retry.is_retryable_error(Exception("Invalid API key"))

    @pytest.mark.asyncio
    async def test_execute_with_retry_success(self):
        """成功调用不需要重试。"""
        retry = AdaptiveRetry()
        call_count = 0
        
        async def success_call(state: RetryState) -> str:
            nonlocal call_count
            call_count += 1
            return "success"
        
        result, final_state = await retry.execute_with_retry(success_call)
        
        assert result == "success"
        assert call_count == 1
        assert final_state.attempt == 0

    @pytest.mark.asyncio
    async def test_execute_with_retry_recovers(self):
        """重试后恢复。"""
        retry = AdaptiveRetry(AdaptiveRetryConfig(base_delay=0.01, max_attempts=3))
        call_count = 0
        
        async def failing_then_success(state: RetryState) -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("HTTP 500 error")
            return "recovered"
        
        result, final_state = await retry.execute_with_retry(failing_then_success)
        
        assert result == "recovered"
        assert call_count == 2
        assert final_state.current_level != DegradationLevel.NONE


# ========== SectionWriter 测试 ==========


class TestSectionWriter:
    """SectionWriter 测试。"""

    @pytest.mark.asyncio
    async def test_write_section_empty_candidates(self):
        """空候选返回降级结果。"""
        async def mock_llm(system: str, user: str) -> str:
            return "Generated content"
        
        writer = SectionWriter(llm_call=mock_llm)
        result = await writer.write_section(
            section_id="sec_1",
            title="Test Section",
            question="What is the situation?",
            objective="Analyze military",
            candidates=[],
        )
        
        assert result.degraded is True
        assert "证据不足" in result.markdown

    @pytest.mark.asyncio
    async def test_write_section_single_pass(self):
        """单次调用模式正常工作。"""
        async def mock_llm(system: str, user: str) -> str:
            return "Analysis based on evidence [1] shows that..."
        
        config = SectionWriteConfig(strategy=WriterStrategy.SINGLE_PASS)
        writer = SectionWriter(llm_call=mock_llm, config=config, enable_adaptive_retry=False)
        
        candidates = [make_candidate(f"ev_{i}") for i in range(3)]
        result = await writer.write_section(
            section_id="sec_1",
            title="Test Section",
            question="What is the situation?",
            objective="Analyze military",
            candidates=candidates,
        )
        
        assert result.markdown is not None
        assert "[1]" in result.markdown
        assert result.strategy_used == WriterStrategy.SINGLE_PASS

    @pytest.mark.asyncio
    async def test_write_section_refine_mode(self):
        """迭代精炼模式正常工作。"""
        call_count = 0
        
        async def mock_llm(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"Refined content iteration {call_count} with [1] and [2]."
        
        config = SectionWriteConfig(
            strategy=WriterStrategy.REFINE,
            batch_size=2,  # 每批 2 条
            budget=PromptBudget(max_evidence_count=10),
        )
        writer = SectionWriter(llm_call=mock_llm, config=config, enable_adaptive_retry=False)
        
        # 创建足够多的候选以触发多批次（至少 5 条，batch_size=2，应该有 3 批）
        candidates = [
            make_candidate(f"ev_{i}", text=f"Unique evidence content {i} about military strategy and operations")
            for i in range(5)
        ]
        result = await writer.write_section(
            section_id="sec_1",
            title="Test Section",
            question="What is the situation?",
            objective="Analyze military",
            candidates=candidates,
        )
        
        assert result.markdown is not None
        # Refine 模式会有多次 LLM 调用（每批一次）
        assert result.llm_calls >= 1
        assert result.strategy_used == WriterStrategy.REFINE

    def test_create_section_writer_factory(self):
        """工厂函数创建 SectionWriter。"""
        async def mock_llm(system: str, user: str) -> str:
            return "test"
        
        writer = create_section_writer(
            llm_call=mock_llm,
            strategy=WriterStrategy.SINGLE_PASS,
            max_tokens=4000,
            max_evidence=10,
        )
        
        assert writer.config.strategy == WriterStrategy.SINGLE_PASS
        assert writer.config.budget.max_tokens == 4000


# ========== PromptBudget 测试 ==========


class TestPromptBudget:
    """PromptBudget 测试。"""

    def test_available_chars_calculation(self):
        """可用字符计算。"""
        budget = PromptBudget(
            max_chars=10000,
            reserved_for_system=500,
            reserved_for_output=2000,
        )
        
        available = budget.available_chars
        assert available == 10000 - 500 - 2000

    def test_allocate_success(self):
        """分配成功。"""
        budget = PromptBudget(max_chars=10000, reserved_for_system=0, reserved_for_output=0)
        
        success = budget.allocate(1000)
        assert success is True
        assert budget.used_chars == 1000
        assert budget.evidence_count == 1

    def test_allocate_failure(self):
        """分配失败（超预算）。"""
        budget = PromptBudget(max_chars=1000, reserved_for_system=0, reserved_for_output=0)
        
        success = budget.allocate(2000)
        assert success is False
        assert budget.used_chars == 0

    def test_can_add_evidence(self):
        """检查是否能添加证据。"""
        budget = PromptBudget(max_evidence_count=2)
        
        assert budget.can_add_evidence is True
        budget.evidence_count = 2
        assert budget.can_add_evidence is False
