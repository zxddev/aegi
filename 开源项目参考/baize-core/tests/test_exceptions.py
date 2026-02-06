"""异常层次结构测试。

验证统一异常层次结构的继承关系和基本功能。
"""

from __future__ import annotations

import pytest

from baize_core.exceptions import (
    AdapterError,
    BaizeCoreError,
    BudgetError,
    BudgetExhaustedError,
    CacheError,
    DatabaseError,
    EvidenceValidationError,
    ExternalApiError,
    HumanReviewRequiredError,
    LlmApiError,
    LlmError,
    LlmTimeoutError,
    McpError,
    MinioError,
    OpenSearchError,
    ParseError,
    PolicyDeniedError,
    PolicyError,
    StorageError,
    StructuredGenerationError,
    ToolError,
    ToolInvocationError,
    ToolTimeoutError,
    ValidationError,
    VectorStoreError,
    Z3ValidationError,
)
from baize_core.schemas.policy import ActionType


class TestExceptionHierarchy:
    """测试异常继承关系。"""

    def test_all_exceptions_inherit_from_base(self) -> None:
        """所有项目异常都应继承自 BaizeCoreError。"""
        exceptions = [
            PolicyError,
            PolicyDeniedError,
            HumanReviewRequiredError,
            LlmError,
            LlmApiError,
            LlmTimeoutError,
            StructuredGenerationError,
            ToolError,
            ToolInvocationError,
            ToolTimeoutError,
            McpError,
            StorageError,
            DatabaseError,
            MinioError,
            VectorStoreError,
            CacheError,
            OpenSearchError,
            AdapterError,
            ExternalApiError,
            ParseError,
            ValidationError,
            Z3ValidationError,
            EvidenceValidationError,
            BudgetError,
            BudgetExhaustedError,
        ]
        for exc_class in exceptions:
            assert issubclass(exc_class, BaizeCoreError), (
                f"{exc_class.__name__} 应继承自 BaizeCoreError"
            )

    def test_policy_exceptions_hierarchy(self) -> None:
        """策略异常层次结构。"""
        assert issubclass(PolicyDeniedError, PolicyError)
        assert issubclass(HumanReviewRequiredError, PolicyError)

    def test_llm_exceptions_hierarchy(self) -> None:
        """LLM 异常层次结构。"""
        assert issubclass(LlmApiError, LlmError)
        assert issubclass(LlmTimeoutError, LlmError)
        assert issubclass(StructuredGenerationError, LlmError)

    def test_tool_exceptions_hierarchy(self) -> None:
        """工具异常层次结构。"""
        assert issubclass(ToolInvocationError, ToolError)
        assert issubclass(ToolTimeoutError, ToolError)
        assert issubclass(McpError, ToolError)

    def test_storage_exceptions_hierarchy(self) -> None:
        """存储异常层次结构。"""
        assert issubclass(DatabaseError, StorageError)
        assert issubclass(MinioError, StorageError)
        assert issubclass(VectorStoreError, StorageError)
        assert issubclass(CacheError, StorageError)
        assert issubclass(OpenSearchError, StorageError)


class TestPolicyDeniedError:
    """测试 PolicyDeniedError。"""

    def test_attributes(self) -> None:
        """测试异常属性。"""
        exc = PolicyDeniedError(ActionType.MODEL_CALL, "模型未在白名单")
        assert exc.action == ActionType.MODEL_CALL
        assert exc.reason == "模型未在白名单"
        assert "model_call" in str(exc)
        assert "模型未在白名单" in str(exc)


class TestHumanReviewRequiredError:
    """测试 HumanReviewRequiredError。"""

    def test_attributes(self) -> None:
        """测试异常属性。"""
        exc = HumanReviewRequiredError("review_123")
        assert exc.review_id == "review_123"
        assert "review_123" in str(exc)


class TestStructuredGenerationError:
    """测试 StructuredGenerationError。"""

    def test_attributes(self) -> None:
        """测试异常属性。"""
        exc = StructuredGenerationError(
            message="校验失败",
            raw_text='{"invalid": json}',
            validation_errors=["字段缺失", "类型错误"],
            retries=3,
        )
        assert str(exc) == "校验失败"
        assert exc.raw_text == '{"invalid": json}'
        assert exc.validation_errors == ["字段缺失", "类型错误"]
        assert exc.retries == 3

    def test_default_values(self) -> None:
        """测试默认值。"""
        exc = StructuredGenerationError("简单错误")
        assert exc.raw_text == ""
        assert exc.validation_errors == []
        assert exc.retries == 0


class TestBudgetExhaustedError:
    """测试 BudgetExhaustedError。"""

    def test_attributes(self) -> None:
        """测试异常属性。"""
        exc = BudgetExhaustedError("token", remaining=100, required=500)
        assert exc.resource == "token"
        assert exc.remaining == 100
        assert exc.required == 500
        assert "token" in str(exc)
        assert "100" in str(exc)
        assert "500" in str(exc)


class TestExceptionCatching:
    """测试异常捕获场景。"""

    def test_catch_by_base_class(self) -> None:
        """可以通过基类捕获所有项目异常。"""
        with pytest.raises(BaizeCoreError):
            raise LlmApiError("测试错误")

        with pytest.raises(BaizeCoreError):
            raise ToolInvocationError("测试错误")

    def test_catch_by_category(self) -> None:
        """可以按类别捕获异常。"""
        with pytest.raises(LlmError):
            raise LlmApiError("API 错误")

        with pytest.raises(LlmError):
            raise StructuredGenerationError("生成失败")

        with pytest.raises(StorageError):
            raise DatabaseError("连接失败")
