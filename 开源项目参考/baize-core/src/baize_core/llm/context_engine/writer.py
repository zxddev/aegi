"""章节写作器（SectionWriter）。

编排证据选择、压缩、预算管理，调用 LLM 生成章节内容。
支持 single-pass 和 map-reduce 两种策略。
集成自适应重试机制，在 LLM 失败时自动降级。
提供 Prometheus 可观测性指标。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from baize_core.llm.context_engine.adaptive_retry import (
    AdaptiveRetry,
    AdaptiveRetryConfig,
    DegradationLevel,
    RetryState,
    compute_degraded_params,
)
from baize_core.llm.context_engine.budgeter import (
    BudgetAction,
    BudgeterConfig,
    PromptBudgeter,
)
from baize_core.llm.context_engine.compressor import (
    CompressorConfig,
    EvidenceCompressor,
)
from baize_core.llm.context_engine.schemas import (
    CompressionMode,
    EvidenceCandidate,
    EvidenceSnippet,
    PromptBudget,
    SectionWriteConfig,
    SectionWriteResult,
    WriterStrategy,
)
from baize_core.llm.context_engine.selector import (
    EvidenceSelector,
    SelectorConfig,
)
from baize_core.llm.context_engine.metrics import (
    record_evidence_selection,
    record_budget_decision,
    record_section_write,
    record_adaptive_retry,
)
from baize_core.prompts.profiles import get_prompt_profile

logger = logging.getLogger(__name__)


class LlmCallable(Protocol):
    """LLM 调用协议。"""

    async def __call__(self, system: str, user: str) -> str:
        """调用 LLM。

        Args:
            system: 系统消息
            user: 用户消息

        Returns:
            LLM 响应
        """
        ...


# Prompt 由 prompts/profiles.py 提供（按 profile 动态选择）


@dataclass
class SectionWriter:
    """章节写作器。

    编排完整的章节写作流程：
    1. 选择证据 (EvidenceSelector)
    2. 压缩证据 (EvidenceCompressor)
    3. 管理预算 (PromptBudgeter)
    4. 调用 LLM 生成内容
    5. 处理失败和自适应降级 (AdaptiveRetry)
    """

    llm_call: LlmCallable
    config: SectionWriteConfig = field(default_factory=SectionWriteConfig)
    enable_adaptive_retry: bool = True  # 是否启用自适应重试
    
    # 内部组件
    _selector: EvidenceSelector = field(init=False)
    _compressor: EvidenceCompressor = field(init=False)
    _budgeter: PromptBudgeter = field(init=False)
    _adaptive_retry: AdaptiveRetry = field(init=False)

    def __post_init__(self) -> None:
        """初始化内部组件。"""
        self._selector = EvidenceSelector(SelectorConfig())
        self._compressor = EvidenceCompressor(CompressorConfig(
            mode=self.config.compression_mode,
        ))
        self._budgeter = PromptBudgeter(BudgeterConfig())
        self._adaptive_retry = AdaptiveRetry(AdaptiveRetryConfig())

    async def write_section(
        self,
        section_id: str,
        title: str,
        question: str,
        objective: str,
        candidates: list[EvidenceCandidate],
        *,
        prompt_profile: str = "default",
        user_context: str | None = None,
    ) -> SectionWriteResult:
        """写作章节。

        Args:
            section_id: 章节 ID
            title: 章节标题
            question: 章节问题
            objective: 任务目标
            candidates: 证据候选列表

        Returns:
            写作结果
        """
        start_time = time.time()
        
        logger.info(
            "SectionWriter: 开始写作章节 %s, 候选证据 %d 条, 策略 %s",
            section_id, len(candidates), self.config.strategy.value
        )
        
        if not candidates:
            result = SectionWriteResult(
                section_id=section_id,
                markdown="证据不足，无法生成分析。",
                citations_used=[],
                evidence_uids_used=[],
                degraded=True,
                degradation_reason="无可用证据",
            )
            # 记录指标
            record_section_write(
                strategy=self.config.strategy.value,
                success=False,
                duration_seconds=time.time() - start_time,
                llm_calls=0,
                output_chars=0,
                section_id=section_id,
            )
            return result
        
        # 根据策略选择写作方法
        if self.config.strategy == WriterStrategy.SINGLE_PASS:
            result = await self._write_single_pass(
                section_id,
                title,
                question,
                objective,
                candidates,
                prompt_profile=prompt_profile,
                user_context=user_context,
            )
        elif self.config.strategy == WriterStrategy.MAP_REDUCE:
            result = await self._write_map_reduce(
                section_id,
                title,
                question,
                objective,
                candidates,
                prompt_profile=prompt_profile,
                user_context=user_context,
            )
        else:
            # REFINE 模式
            result = await self._write_refine(
                section_id,
                title,
                question,
                objective,
                candidates,
                prompt_profile=prompt_profile,
                user_context=user_context,
            )
        
        # 记录指标
        record_section_write(
            strategy=self.config.strategy.value,
            success=not result.degraded,
            duration_seconds=time.time() - start_time,
            llm_calls=result.llm_calls,
            output_chars=result.total_output_chars,
            section_id=section_id,
        )
        
        return result

    async def _write_single_pass(
        self,
        section_id: str,
        title: str,
        question: str,
        objective: str,
        candidates: list[EvidenceCandidate],
        *,
        prompt_profile: str,
        user_context: str | None,
    ) -> SectionWriteResult:
        """单次调用模式（带自适应重试）。"""
        original_evidence_count = self.config.budget.max_evidence_count
        original_max_chars = self.config.budget.max_chars_per_evidence
        
        async def _attempt_write(state: RetryState) -> str:
            """带降级参数的写作尝试。"""
            # 根据降级状态调整参数
            evidence_count, max_chars_per = compute_degraded_params(
                state, original_evidence_count, original_max_chars
            )
            
            # 1. 选择证据
            selected = self._selector.select(
                candidates,
                section_question=question,
                top_k=evidence_count,
            )
            
            # 2. 创建预算
            budget = self._budgeter.create_budget(
                max_tokens=self.config.budget.max_tokens,
                evidence_count_hint=len(selected),
            )
            
            # 3. 分配预算并压缩
            allocations = self._budgeter.allocate_budget(budget, len(selected))
            snippets: list[EvidenceSnippet] = []
            
            for i, candidate in enumerate(selected):
                base_chars = allocations[i] if i < len(allocations) else max_chars_per
                # 应用降级系数
                actual_chars = min(base_chars, max_chars_per)
                snippet = self._compressor.compress(
                    candidate,
                    citation=i + 1,
                    max_chars=actual_chars,
                    section_question=question,
                )
                snippets.append(snippet)
            
            # 4. 检查预算
            decision = self._budgeter.check_budget(budget, snippets, additional_chars=500)
            if decision.action != BudgetAction.ACCEPT:
                logger.warning("章节 %s 预算调整: %s", section_id, decision.reason)
                snippets = self._budgeter.apply_budget_decision(decision, snippets)
            
            # 5. 构建 prompt
            nonlocal _last_snippets, _last_prompt
            _last_snippets = snippets
            evidence_block = "\n\n".join(s.to_citation_block() for s in snippets)
            profile = get_prompt_profile(prompt_profile)
            context_text = (
                user_context.strip()
                if isinstance(user_context, str) and user_context.strip()
                else "（无）"
            )
            user_prompt = profile.user_template.format(
                objective=objective,
                title=title,
                question=question,
                user_context=context_text,
                evidence_block=evidence_block,
                min_paragraphs=self.config.min_paragraphs,
                max_paragraphs=self.config.max_paragraphs,
            )
            _last_prompt = user_prompt
            
            # 6. 调用 LLM
            response = await self.llm_call(profile.system, user_prompt)
            return response.strip()
        
        def _on_degradation(state: RetryState) -> None:
            """降级回调。"""
            logger.warning(
                "章节 %s 降级到 %s（尝试 %d/%d）",
                section_id, state.current_level.value,
                state.attempt, state.total_attempts
            )
        
        # 用于捕获最后使用的 snippets 和 prompt
        _last_snippets: list[EvidenceSnippet] = []
        _last_prompt: str = ""
        
        if self.enable_adaptive_retry:
            try:
                markdown, final_state = await self._adaptive_retry.execute_with_retry(
                    _attempt_write,
                    on_degradation=_on_degradation,
                )
                
                # 提取使用的引用
                citations_used = self._extract_citations(markdown, len(_last_snippets))
                evidence_uids = [s.evidence_uid for s in _last_snippets if s.citation in citations_used]
                
                return SectionWriteResult(
                    section_id=section_id,
                    markdown=markdown,
                    citations_used=citations_used,
                    evidence_uids_used=evidence_uids,
                    llm_calls=final_state.attempt + 1,
                    total_input_chars=len(_last_prompt),
                    total_output_chars=len(markdown),
                    strategy_used=WriterStrategy.SINGLE_PASS,
                    degraded=final_state.current_level != DegradationLevel.NONE,
                    degradation_reason=final_state.current_level.value if final_state.current_level != DegradationLevel.NONE else None,
                    metadata={
                        "final_evidence_count": len(_last_snippets),
                        "degradation_level": final_state.current_level.value,
                        "citation_evidence_uid_map": {
                            s.citation: s.evidence_uid
                            for s in _last_snippets
                            if s.citation in citations_used
                        },
                    },
                )
            except Exception as e:
                logger.error("章节 %s 自适应重试耗尽: %s", section_id, e)
                return SectionWriteResult(
                    section_id=section_id,
                    markdown=f"生成失败（重试耗尽）: {e}",
                    citations_used=[],
                    evidence_uids_used=[],
                    llm_calls=5,
                    degraded=True,
                    degradation_reason=str(e),
                )
        else:
            # 不启用自适应重试，直接调用
            try:
                state = RetryState()
                markdown = await _attempt_write(state)
                
                citations_used = self._extract_citations(markdown, len(_last_snippets))
                evidence_uids = [s.evidence_uid for s in _last_snippets if s.citation in citations_used]
                
                return SectionWriteResult(
                    section_id=section_id,
                    markdown=markdown,
                    citations_used=citations_used,
                    evidence_uids_used=evidence_uids,
                    llm_calls=1,
                    total_input_chars=len(_last_prompt),
                    total_output_chars=len(markdown),
                    strategy_used=WriterStrategy.SINGLE_PASS,
                    metadata={
                        "final_evidence_count": len(_last_snippets),
                        "degradation_level": "none",
                        "citation_evidence_uid_map": {
                            s.citation: s.evidence_uid
                            for s in _last_snippets
                            if s.citation in citations_used
                        },
                    },
                )
            except Exception as e:
                logger.error("章节 %s LLM 调用失败: %s", section_id, e)
                return SectionWriteResult(
                    section_id=section_id,
                    markdown=f"生成失败: {e}",
                    citations_used=[],
                    evidence_uids_used=[],
                    llm_calls=1,
                    degraded=True,
                    degradation_reason=str(e),
                )

    async def _write_refine(
        self,
        section_id: str,
        title: str,
        question: str,
        objective: str,
        candidates: list[EvidenceCandidate],
        *,
        prompt_profile: str,
        user_context: str | None,
    ) -> SectionWriteResult:
        """迭代精炼模式。"""
        profile = get_prompt_profile(prompt_profile)
        context_text = (
            user_context.strip()
            if isinstance(user_context, str) and user_context.strip()
            else "（无）"
        )
        # 1. 选择并分批
        selected = self._selector.select(
            candidates,
            section_question=question,
            top_k=self.config.budget.max_evidence_count,
        )
        
        batch_size = self.config.batch_size
        batches = [
            selected[i:i + batch_size]
            for i in range(0, len(selected), batch_size)
        ]
        
        logger.info(
            "章节 %s: %d 条证据分成 %d 批次（Refine 模式）",
            section_id, len(selected), len(batches)
        )
        
        # 2. 迭代处理
        current_content = ""
        all_snippets: list[EvidenceSnippet] = []
        llm_calls = 0
        total_input_chars = 0
        total_output_chars = 0
        citation_offset = 1
        
        for batch_idx, batch in enumerate(batches):
            is_first = batch_idx == 0
            
            # 压缩当前批次
            snippets = self._compressor.compress_batch(
                batch,
                start_citation=citation_offset,
                max_chars_per_item=self.config.budget.max_chars_per_evidence,
                section_question=question,
            )
            all_snippets.extend(snippets)
            citation_offset += len(snippets)
            
            # 构建 prompt
            evidence_block = "\n\n".join(s.to_citation_block() for s in snippets)
            
            if is_first:
                user_prompt = profile.user_template.format(
                    objective=objective,
                    title=title,
                    question=question,
                    user_context=context_text,
                    evidence_block=evidence_block,
                    min_paragraphs=self.config.min_paragraphs,
                    max_paragraphs=self.config.max_paragraphs,
                )
            else:
                user_prompt = profile.refine_template.format(
                    objective=objective,
                    title=title,
                    user_context=context_text,
                    existing_content=current_content[:3000],
                    evidence_block=evidence_block,
                )
            
            # 调用 LLM
            try:
                response = await self.llm_call(profile.system, user_prompt)
                current_content = response.strip()
                llm_calls += 1
                total_input_chars += len(user_prompt)
                total_output_chars += len(response)
            except Exception as e:
                logger.warning("章节 %s 批次 %d 失败: %s", section_id, batch_idx, e)
                if is_first:
                    return SectionWriteResult(
                        section_id=section_id,
                        markdown=f"生成失败: {e}",
                        citations_used=[],
                        evidence_uids_used=[],
                        llm_calls=llm_calls,
                        degraded=True,
                        degradation_reason=str(e),
                    )
                break
            
            logger.debug(
                "章节 %s 批次 %d/%d 完成，当前内容长度: %d",
                section_id, batch_idx + 1, len(batches), len(current_content)
            )
        
        # 提取引用
        citations_used = self._extract_citations(current_content, len(all_snippets))
        evidence_uids = [s.evidence_uid for s in all_snippets if s.citation in citations_used]
        
        return SectionWriteResult(
            section_id=section_id,
            markdown=current_content,
            citations_used=citations_used,
            evidence_uids_used=evidence_uids,
            llm_calls=llm_calls,
            total_input_chars=total_input_chars,
            total_output_chars=total_output_chars,
            strategy_used=WriterStrategy.REFINE,
            metadata={
                "final_evidence_count": len(all_snippets),
                "degradation_level": "none",
                "citation_evidence_uid_map": {
                    s.citation: s.evidence_uid
                    for s in all_snippets
                    if s.citation in citations_used
                },
            },
        )

    async def _write_map_reduce(
        self,
        section_id: str,
        title: str,
        question: str,
        objective: str,
        candidates: list[EvidenceCandidate],
        *,
        prompt_profile: str,
        user_context: str | None,
    ) -> SectionWriteResult:
        """Map-Reduce 模式。

        Map: 为每批证据生成要点
        Reduce: 综合所有要点生成最终内容
        """
        # 当前简化实现：使用 refine 模式
        # TODO: 完整实现 Map-Reduce，并行处理 Map 阶段
        return await self._write_refine(
            section_id,
            title,
            question,
            objective,
            candidates,
            prompt_profile=prompt_profile,
            user_context=user_context,
        )

    def _extract_citations(self, text: str, max_citation: int) -> list[int]:
        """从文本中提取引用编号。"""
        import re
        pattern = r'\[(\d+)\]'
        matches = re.findall(pattern, text)
        citations = set()
        for m in matches:
            num = int(m)
            if 1 <= num <= max_citation:
                citations.add(num)
        return sorted(citations)


def create_section_writer(
    llm_call: LlmCallable,
    strategy: WriterStrategy = WriterStrategy.SINGLE_PASS,
    max_tokens: int = 8000,
    max_evidence: int = 15,
) -> SectionWriter:
    """创建 SectionWriter 实例的便捷函数。

    Args:
        llm_call: LLM 调用函数
        strategy: 写作策略
        max_tokens: 最大 token 数
        max_evidence: 最大证据数

    Returns:
        SectionWriter 实例
    """
    config = SectionWriteConfig(
        strategy=strategy,
        budget=PromptBudget(
            max_tokens=max_tokens,
            max_chars=max_tokens * 4,
            max_evidence_count=max_evidence,
        ),
    )
    return SectionWriter(llm_call=llm_call, config=config)
