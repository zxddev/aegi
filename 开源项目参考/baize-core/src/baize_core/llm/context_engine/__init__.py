"""上下文工程层（Context Engineering Layer）。

提供 STORM 报告生成的上下文管理能力：
- EvidenceSelector: 证据选择与排序
- EvidenceCompressor: 证据压缩与摘要
- PromptBudgeter: Prompt 预算管理
- SectionWriter: 章节写作策略
"""

from baize_core.llm.context_engine.schemas import (
    CompressionMode,
    EvidenceCandidate,
    EvidenceSnippet,
    FactCard,
    PromptBudget,
    SectionWriteConfig,
    SectionWriteResult,
    WriterStrategy,
)
from baize_core.llm.context_engine.selector import (
    EvidenceSelector,
    SelectorConfig,
    create_candidates_from_evidence_chain,
)
from baize_core.llm.context_engine.compressor import (
    EvidenceCompressor,
    CompressorConfig,
    clear_compression_cache,
)
from baize_core.llm.context_engine.budgeter import (
    PromptBudgeter,
    BudgeterConfig,
    BudgetAction,
    BudgetDecision,
)
from baize_core.llm.context_engine.writer import (
    SectionWriter,
    create_section_writer,
)
from baize_core.llm.context_engine.adaptive_retry import (
    AdaptiveRetry,
    AdaptiveRetryConfig,
    DegradationLevel,
    RetryState,
    compute_degraded_params,
)
from baize_core.llm.context_engine.metrics import (
    record_evidence_selection,
    record_compression,
    record_budget_decision,
    record_section_write,
    record_adaptive_retry,
    is_prometheus_available,
)

__all__ = [
    # Schemas
    "CompressionMode",
    "EvidenceCandidate",
    "EvidenceSnippet",
    "FactCard",
    "PromptBudget",
    "SectionWriteConfig",
    "SectionWriteResult",
    "WriterStrategy",
    # Selector
    "EvidenceSelector",
    "SelectorConfig",
    "create_candidates_from_evidence_chain",
    # Compressor
    "EvidenceCompressor",
    "CompressorConfig",
    "clear_compression_cache",
    # Budgeter
    "PromptBudgeter",
    "BudgeterConfig",
    "BudgetAction",
    "BudgetDecision",
    # Writer
    "SectionWriter",
    "create_section_writer",
    # Adaptive Retry
    "AdaptiveRetry",
    "AdaptiveRetryConfig",
    "DegradationLevel",
    "RetryState",
    "compute_degraded_params",
    # Metrics
    "record_evidence_selection",
    "record_compression",
    "record_budget_decision",
    "record_section_write",
    "record_adaptive_retry",
    "is_prometheus_available",
]
