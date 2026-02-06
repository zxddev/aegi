"""baize-core 统一异常层次结构。

提供项目级别的异常基类和分类异常，便于：
1. 捕获具体异常类型而非宽泛的 Exception
2. 统一错误处理和日志记录
3. 保持调用栈信息完整
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from baize_core.schemas.policy import ActionType


class BaizeCoreError(Exception):
    """baize-core 基础异常类。

    所有项目异常都应继承此类，便于统一捕获和处理。
    """

    pass


# =============================================================================
# 策略相关异常
# =============================================================================


class PolicyError(BaizeCoreError):
    """策略相关错误基类。"""

    pass


class PolicyDeniedError(PolicyError):
    """策略拒绝错误。

    当策略引擎拒绝某个操作（模型调用、工具调用、导出等）时抛出。
    """

    def __init__(self, action: ActionType, reason: str) -> None:
        self.action = action
        self.reason = reason
        super().__init__(f"策略拒绝{action.value}调用: {reason}")


class HumanReviewRequiredError(PolicyError):
    """需要人工复核错误。

    当策略引擎要求人工介入审核时抛出。
    """

    def __init__(self, review_id: str) -> None:
        self.review_id = review_id
        super().__init__(f"需要人工复核: {review_id}")


# =============================================================================
# LLM 相关异常
# =============================================================================


class LlmError(BaizeCoreError):
    """LLM 相关错误基类。"""

    pass


class LlmApiError(LlmError):
    """LLM API 调用错误。

    当调用 LLM 提供商 API 失败时抛出（网络错误、认证失败、限流等）。
    """

    pass


class LlmTimeoutError(LlmError):
    """LLM 调用超时错误。"""

    pass


class StructuredGenerationError(LlmError):
    """结构化生成错误。

    当结构化输出生成或校验失败时抛出。

    Attributes:
        message: 错误消息
        raw_text: 原始输出文本
        validation_errors: 校验错误列表
        retries: 已重试次数
    """

    def __init__(
        self,
        message: str,
        raw_text: str = "",
        validation_errors: list[str] | None = None,
        retries: int = 0,
    ) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.validation_errors = validation_errors or []
        self.retries = retries


# =============================================================================
# 工具相关异常
# =============================================================================


class ToolError(BaizeCoreError):
    """工具相关错误基类。"""

    pass


class ToolInvocationError(ToolError):
    """工具调用错误。

    当工具执行失败时抛出。
    """

    pass


class ToolTimeoutError(ToolError):
    """工具调用超时错误。"""

    pass


class McpError(ToolError):
    """MCP 网关错误。

    当 MCP Gateway 调用失败时抛出。
    """

    pass


# =============================================================================
# 存储相关异常
# =============================================================================


class StorageError(BaizeCoreError):
    """存储相关错误基类。"""

    pass


class DatabaseError(StorageError):
    """数据库操作错误。

    当 PostgreSQL 等关系数据库操作失败时抛出。
    """

    pass


class MinioError(StorageError):
    """MinIO 对象存储错误。

    当 MinIO 操作失败时抛出。
    """

    pass


class VectorStoreError(StorageError):
    """向量存储错误。

    当 Qdrant 等向量数据库操作失败时抛出。
    """

    pass


class CacheError(StorageError):
    """缓存操作错误。

    当 Redis 等缓存操作失败时抛出。
    """

    pass


class OpenSearchError(StorageError):
    """OpenSearch 错误。

    当 OpenSearch 操作失败时抛出。
    """

    pass


# =============================================================================
# 适配器相关异常
# =============================================================================


class AdapterError(BaizeCoreError):
    """外部服务适配器错误基类。"""

    pass


class ExternalApiError(AdapterError):
    """外部 API 调用错误。

    当调用外部服务（Firecrawl、Perplexica、SearXNG 等）失败时抛出。
    """

    pass


class ParseError(AdapterError):
    """数据解析错误。

    当解析外部服务返回的数据失败时抛出。
    """

    pass


# =============================================================================
# 验证相关异常
# =============================================================================


class ValidationError(BaizeCoreError):
    """验证错误基类。"""

    pass


class Z3ValidationError(ValidationError):
    """Z3 约束校验错误。

    当 Z3 时间线一致性校验失败时抛出。
    """

    pass


class EvidenceValidationError(ValidationError):
    """证据校验错误。

    当证据链校验失败时抛出。
    """

    pass


# =============================================================================
# 预算相关异常
# =============================================================================


class BudgetError(BaizeCoreError):
    """预算相关错误基类。"""

    pass


class BudgetExhaustedError(BudgetError):
    """预算耗尽异常。

    当 token、调用次数或时间预算耗尽时抛出。
    """

    def __init__(self, resource: str, remaining: int, required: int) -> None:
        self.resource = resource
        self.remaining = remaining
        self.required = required
        super().__init__(f"{resource} 预算不足：剩余 {remaining}，需要 {required}")


# =============================================================================
# 导出所有异常类
# =============================================================================

__all__ = [
    # 基类
    "BaizeCoreError",
    # 策略
    "PolicyError",
    "PolicyDeniedError",
    "HumanReviewRequiredError",
    # LLM
    "LlmError",
    "LlmApiError",
    "LlmTimeoutError",
    "StructuredGenerationError",
    # 工具
    "ToolError",
    "ToolInvocationError",
    "ToolTimeoutError",
    "McpError",
    # 存储
    "StorageError",
    "DatabaseError",
    "MinioError",
    "VectorStoreError",
    "CacheError",
    "OpenSearchError",
    # 适配器
    "AdapterError",
    "ExternalApiError",
    "ParseError",
    # 验证
    "ValidationError",
    "Z3ValidationError",
    "EvidenceValidationError",
    # 预算
    "BudgetError",
    "BudgetExhaustedError",
]
