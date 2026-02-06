"""上下文工程层可观测性指标。

提供 Prometheus 指标用于监控：
- 证据选择与压缩
- 预算使用情况
- 章节写作性能
- 自适应重试与降级
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ========== Prometheus 指标（可选依赖）==========

try:
    from prometheus_client import Counter, Histogram, Gauge

    _PROMETHEUS_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    Counter = None
    Histogram = None
    Gauge = None
    _PROMETHEUS_AVAILABLE = False


def _create_counter(name: str, doc: str, labels: list[str]) -> Any:
    """创建 Counter 指标。"""
    if _PROMETHEUS_AVAILABLE:
        return Counter(name, doc, labels)
    return None


def _create_histogram(name: str, doc: str, labels: list[str], buckets: tuple | None = None) -> Any:
    """创建 Histogram 指标。"""
    if _PROMETHEUS_AVAILABLE:
        kwargs = {"labelnames": labels}
        if buckets:
            kwargs["buckets"] = buckets
        return Histogram(name, doc, **kwargs)
    return None


def _create_gauge(name: str, doc: str, labels: list[str]) -> Any:
    """创建 Gauge 指标。"""
    if _PROMETHEUS_AVAILABLE:
        return Gauge(name, doc, labels)
    return None


# ========== 证据选择指标 ==========

EVIDENCE_SELECTED_TOTAL = _create_counter(
    "baize_context_engine_evidence_selected_total",
    "证据选择总数",
    ["section_id"],
)

EVIDENCE_FILTERED_TOTAL = _create_counter(
    "baize_context_engine_evidence_filtered_total",
    "被过滤的证据数",
    ["reason"],  # low_credibility, low_quality_domain, duplicate
)

EVIDENCE_SELECTION_DURATION = _create_histogram(
    "baize_context_engine_evidence_selection_duration_seconds",
    "证据选择耗时",
    ["section_id"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)


# ========== 证据压缩指标 ==========

EVIDENCE_COMPRESSED_TOTAL = _create_counter(
    "baize_context_engine_evidence_compressed_total",
    "压缩的证据数",
    ["mode"],  # extractive, llm_notes
)

COMPRESSION_RATIO = _create_histogram(
    "baize_context_engine_compression_ratio",
    "压缩率（压缩后/原始）",
    ["mode"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

COMPRESSION_CACHE_HITS = _create_counter(
    "baize_context_engine_compression_cache_hits_total",
    "压缩缓存命中数",
    [],
)

COMPRESSION_CACHE_MISSES = _create_counter(
    "baize_context_engine_compression_cache_misses_total",
    "压缩缓存未命中数",
    [],
)


# ========== 预算管理指标 ==========

BUDGET_USAGE_RATIO = _create_histogram(
    "baize_context_engine_budget_usage_ratio",
    "预算使用率",
    ["section_id"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1),
)

BUDGET_ACTIONS_TOTAL = _create_counter(
    "baize_context_engine_budget_actions_total",
    "预算调整动作数",
    ["action"],  # accept, truncate, reduce_count, summarize
)

PROMPT_TOKEN_ESTIMATE = _create_histogram(
    "baize_context_engine_prompt_token_estimate",
    "Prompt token 估算值",
    ["section_id"],
    buckets=(500, 1000, 2000, 4000, 8000, 16000, 32000),
)


# ========== 章节写作指标 ==========

SECTION_WRITE_TOTAL = _create_counter(
    "baize_context_engine_section_write_total",
    "章节写作总数",
    ["strategy", "success"],  # strategy: single_pass, refine, map_reduce
)

SECTION_WRITE_DURATION = _create_histogram(
    "baize_context_engine_section_write_duration_seconds",
    "章节写作耗时",
    ["strategy"],
    buckets=(1, 2, 5, 10, 20, 30, 60, 120),
)

SECTION_LLM_CALLS = _create_histogram(
    "baize_context_engine_section_llm_calls",
    "每章节 LLM 调用次数",
    ["strategy"],
    buckets=(1, 2, 3, 5, 8, 10, 15, 20),
)

SECTION_OUTPUT_CHARS = _create_histogram(
    "baize_context_engine_section_output_chars",
    "章节输出字符数",
    ["section_id"],
    buckets=(500, 1000, 2000, 4000, 8000, 16000),
)


# ========== 自适应重试指标 ==========

ADAPTIVE_RETRY_TOTAL = _create_counter(
    "baize_context_engine_adaptive_retry_total",
    "自适应重试总数",
    ["final_level"],  # none, light, moderate, aggressive, fallback
)

ADAPTIVE_RETRY_ATTEMPTS = _create_histogram(
    "baize_context_engine_adaptive_retry_attempts",
    "重试次数分布",
    [],
    buckets=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
)

DEGRADATION_EVENTS_TOTAL = _create_counter(
    "baize_context_engine_degradation_events_total",
    "降级事件数",
    ["level", "error_type"],  # level: light, moderate, aggressive
)


# ========== 辅助函数 ==========


def record_evidence_selection(
    section_id: str,
    selected_count: int,
    filtered_low_credibility: int = 0,
    filtered_low_quality: int = 0,
    filtered_duplicate: int = 0,
    duration_seconds: float = 0.0,
) -> None:
    """记录证据选择指标。"""
    if EVIDENCE_SELECTED_TOTAL:
        EVIDENCE_SELECTED_TOTAL.labels(section_id=section_id).inc(selected_count)
    
    if EVIDENCE_FILTERED_TOTAL:
        if filtered_low_credibility > 0:
            EVIDENCE_FILTERED_TOTAL.labels(reason="low_credibility").inc(filtered_low_credibility)
        if filtered_low_quality > 0:
            EVIDENCE_FILTERED_TOTAL.labels(reason="low_quality_domain").inc(filtered_low_quality)
        if filtered_duplicate > 0:
            EVIDENCE_FILTERED_TOTAL.labels(reason="duplicate").inc(filtered_duplicate)
    
    if EVIDENCE_SELECTION_DURATION and duration_seconds > 0:
        EVIDENCE_SELECTION_DURATION.labels(section_id=section_id).observe(duration_seconds)


def record_compression(
    mode: str,
    original_chars: int,
    compressed_chars: int,
    cache_hit: bool = False,
) -> None:
    """记录压缩指标。"""
    if EVIDENCE_COMPRESSED_TOTAL:
        EVIDENCE_COMPRESSED_TOTAL.labels(mode=mode).inc()
    
    if COMPRESSION_RATIO and original_chars > 0:
        ratio = compressed_chars / original_chars
        COMPRESSION_RATIO.labels(mode=mode).observe(ratio)
    
    if cache_hit:
        if COMPRESSION_CACHE_HITS:
            COMPRESSION_CACHE_HITS.inc()
    else:
        if COMPRESSION_CACHE_MISSES:
            COMPRESSION_CACHE_MISSES.inc()


def record_budget_decision(
    section_id: str,
    action: str,
    usage_ratio: float,
    token_estimate: int = 0,
) -> None:
    """记录预算决策指标。"""
    if BUDGET_ACTIONS_TOTAL:
        BUDGET_ACTIONS_TOTAL.labels(action=action).inc()
    
    if BUDGET_USAGE_RATIO:
        BUDGET_USAGE_RATIO.labels(section_id=section_id).observe(usage_ratio)
    
    if PROMPT_TOKEN_ESTIMATE and token_estimate > 0:
        PROMPT_TOKEN_ESTIMATE.labels(section_id=section_id).observe(token_estimate)


def record_section_write(
    strategy: str,
    success: bool,
    duration_seconds: float,
    llm_calls: int,
    output_chars: int,
    section_id: str = "",
) -> None:
    """记录章节写作指标。"""
    if SECTION_WRITE_TOTAL:
        SECTION_WRITE_TOTAL.labels(strategy=strategy, success=str(success)).inc()
    
    if SECTION_WRITE_DURATION:
        SECTION_WRITE_DURATION.labels(strategy=strategy).observe(duration_seconds)
    
    if SECTION_LLM_CALLS:
        SECTION_LLM_CALLS.labels(strategy=strategy).observe(llm_calls)
    
    if SECTION_OUTPUT_CHARS and section_id:
        SECTION_OUTPUT_CHARS.labels(section_id=section_id).observe(output_chars)


def record_adaptive_retry(
    final_level: str,
    attempts: int,
    error_type: str = "",
) -> None:
    """记录自适应重试指标。"""
    if ADAPTIVE_RETRY_TOTAL:
        ADAPTIVE_RETRY_TOTAL.labels(final_level=final_level).inc()
    
    if ADAPTIVE_RETRY_ATTEMPTS:
        ADAPTIVE_RETRY_ATTEMPTS.observe(attempts)
    
    if DEGRADATION_EVENTS_TOTAL and final_level != "none":
        DEGRADATION_EVENTS_TOTAL.labels(level=final_level, error_type=error_type).inc()


# ========== 指标状态 ==========


@dataclass
class ContextEngineStats:
    """上下文工程统计快照。"""

    evidence_selected: int = 0
    evidence_filtered: int = 0
    compression_cache_hits: int = 0
    sections_written: int = 0
    degradations: int = 0
    avg_compression_ratio: float = 0.0
    avg_budget_usage: float = 0.0


def get_stats() -> ContextEngineStats:
    """获取当前统计（用于调试/监控）。"""
    # 这里返回空统计，实际值需要从 Prometheus 获取
    return ContextEngineStats()


def is_prometheus_available() -> bool:
    """检查 Prometheus 是否可用。"""
    return _PROMETHEUS_AVAILABLE
