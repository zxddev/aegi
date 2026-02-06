"""自适应重试机制（AdaptiveRetry）。

当 LLM 调用失败时，不只是"等一等重试"，而是缩小上下文再重试。
支持多种降级策略：减少证据数量、截断每条证据、切换压缩模式等。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class DegradationLevel(str, Enum):
    """降级等级。"""

    NONE = "none"  # 无降级
    LIGHT = "light"  # 轻度：截断证据
    MODERATE = "moderate"  # 中度：减少证据数量
    AGGRESSIVE = "aggressive"  # 激进：仅保留摘要
    FALLBACK = "fallback"  # 最终：极简模式


@dataclass
class RetryState:
    """重试状态。"""

    attempt: int = 0
    total_attempts: int = 5
    current_level: DegradationLevel = DegradationLevel.NONE
    last_error: Exception | None = None
    
    # 当前降级参数
    evidence_count_factor: float = 1.0  # 证据数量系数
    excerpt_chars_factor: float = 1.0  # 摘录长度系数
    use_extractive_only: bool = False  # 强制使用抽取模式
    
    @property
    def should_retry(self) -> bool:
        """是否应该重试。"""
        return self.attempt < self.total_attempts

    @property
    def is_final_attempt(self) -> bool:
        """是否最后一次尝试。"""
        return self.attempt >= self.total_attempts - 1


@dataclass
class AdaptiveRetryConfig:
    """自适应重试配置。"""

    max_attempts: int = 5
    base_delay: float = 1.0  # 基础延迟（秒）
    max_delay: float = 30.0  # 最大延迟（秒）
    
    # 降级阈值
    light_degradation_after: int = 1  # 第几次失败后开始轻度降级
    moderate_degradation_after: int = 2  # 中度降级
    aggressive_degradation_after: int = 3  # 激进降级
    
    # 降级参数
    light_excerpt_factor: float = 0.8  # 轻度：摘录缩短到 80%
    moderate_count_factor: float = 0.7  # 中度：证据数量减少到 70%
    moderate_excerpt_factor: float = 0.6  # 中度：摘录缩短到 60%
    aggressive_count_factor: float = 0.5  # 激进：证据数量减少到 50%
    aggressive_excerpt_factor: float = 0.4  # 激进：摘录缩短到 40%
    
    # 可重试的错误模式
    retryable_patterns: tuple[str, ...] = (
        "500", "502", "503", "504",  # 服务器错误
        "context", "token", "length",  # 上下文/token 相关
        "timeout", "timed out",  # 超时
        "rate", "limit", "quota",  # 限流
        "connection", "reset", "refused",  # 网络
    )


@dataclass
class AdaptiveRetry:
    """自适应重试器。

    当 LLM 调用失败时：
    1. 分析错误类型
    2. 决定降级策略
    3. 调整上下文参数
    4. 重试调用
    """

    config: AdaptiveRetryConfig = field(default_factory=AdaptiveRetryConfig)

    async def execute_with_retry(
        self,
        call_fn: Callable[[RetryState], Awaitable[str]],
        on_degradation: Callable[[RetryState], None] | None = None,
    ) -> tuple[str, RetryState]:
        """执行带自适应重试的调用。

        Args:
            call_fn: 调用函数，接收 RetryState 以调整参数
            on_degradation: 降级回调，用于记录/通知

        Returns:
            (结果文本, 最终重试状态)

        Raises:
            最后一次失败的异常
        """
        state = RetryState(total_attempts=self.config.max_attempts)
        delay = self.config.base_delay
        
        while state.should_retry:
            try:
                result = await call_fn(state)
                return result, state
            except Exception as e:
                state.last_error = e
                state.attempt += 1
                
                if not state.should_retry:
                    logger.error(
                        "自适应重试耗尽（%d 次尝试），降级级别: %s, 错误: %s",
                        state.attempt, state.current_level.value, e
                    )
                    raise
                
                # 分析错误并决定降级策略
                self._apply_degradation(state, e)
                
                if on_degradation:
                    on_degradation(state)
                
                logger.warning(
                    "自适应重试（尝试 %d/%d），降级级别: %s，%.1f秒后重试: %s",
                    state.attempt, state.total_attempts,
                    state.current_level.value, delay, e
                )
                
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.config.max_delay)
        
        # 不应该到达这里
        if state.last_error:
            raise state.last_error
        raise RuntimeError("自适应重试异常终止")

    def _apply_degradation(self, state: RetryState, error: Exception) -> None:
        """根据错误和尝试次数应用降级策略。"""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # 检查是否是上下文相关错误（需要更激进的降级）
        is_context_error = any(
            pattern in error_str or pattern in error_type
            for pattern in ("context", "token", "length", "limit")
        )
        
        attempt = state.attempt
        
        if is_context_error:
            # 上下文错误：直接跳到中度或激进降级
            if attempt <= 1:
                self._set_moderate_degradation(state)
            else:
                self._set_aggressive_degradation(state)
        else:
            # 常规错误：渐进式降级
            if attempt >= self.config.aggressive_degradation_after:
                self._set_aggressive_degradation(state)
            elif attempt >= self.config.moderate_degradation_after:
                self._set_moderate_degradation(state)
            elif attempt >= self.config.light_degradation_after:
                self._set_light_degradation(state)

    def _set_light_degradation(self, state: RetryState) -> None:
        """应用轻度降级。"""
        state.current_level = DegradationLevel.LIGHT
        state.excerpt_chars_factor = self.config.light_excerpt_factor
        state.evidence_count_factor = 1.0
        state.use_extractive_only = False

    def _set_moderate_degradation(self, state: RetryState) -> None:
        """应用中度降级。"""
        state.current_level = DegradationLevel.MODERATE
        state.excerpt_chars_factor = self.config.moderate_excerpt_factor
        state.evidence_count_factor = self.config.moderate_count_factor
        state.use_extractive_only = True

    def _set_aggressive_degradation(self, state: RetryState) -> None:
        """应用激进降级。"""
        state.current_level = DegradationLevel.AGGRESSIVE
        state.excerpt_chars_factor = self.config.aggressive_excerpt_factor
        state.evidence_count_factor = self.config.aggressive_count_factor
        state.use_extractive_only = True

    def is_retryable_error(self, error: Exception) -> bool:
        """检查错误是否可重试。"""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        return any(
            pattern in error_str or pattern in error_type
            for pattern in self.config.retryable_patterns
        )


def compute_degraded_params(
    state: RetryState,
    original_evidence_count: int,
    original_max_chars: int,
) -> tuple[int, int]:
    """根据重试状态计算降级后的参数。

    Args:
        state: 重试状态
        original_evidence_count: 原始证据数量
        original_max_chars: 原始每条证据最大字符数

    Returns:
        (降级后证据数量, 降级后每条最大字符数)
    """
    new_count = max(1, int(original_evidence_count * state.evidence_count_factor))
    new_chars = max(100, int(original_max_chars * state.excerpt_chars_factor))
    
    return new_count, new_chars
