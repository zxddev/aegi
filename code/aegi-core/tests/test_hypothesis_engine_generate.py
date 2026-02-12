# Author: msq
"""Hypothesis generate 冷启动行为测试。"""

from __future__ import annotations

import pytest

from aegi_core.contracts.llm_governance import BudgetContext
from aegi_core.services.hypothesis_engine import generate_hypotheses


class _EmptyLLM:
    """模拟 LLM 返回空列表。"""

    async def invoke_as_backend(self, request, prompt):  # type: ignore[no-untyped-def]
        return []


class _FailingLLM:
    """模拟 LLM 调用抛异常。"""

    async def invoke_as_backend(self, request, prompt):  # type: ignore[no-untyped-def]
        raise RuntimeError("llm down")


@pytest.mark.asyncio
async def test_generate_hypotheses_uses_fallback_when_llm_returns_empty() -> None:
    llm = _EmptyLLM()
    results, action, _, _ = await generate_hypotheses(
        assertions=[],
        source_claims=[],
        case_uid="case_test",
        llm=llm,  # type: ignore[arg-type]
        budget=BudgetContext(max_tokens=4096, max_cost_usd=1.0),
        context={"background_text": "cold-start"},
    )

    assert len(results) == 3
    assert all(r.hypothesis_text for r in results)
    assert action.outputs["hypothesis_count"] == 3


@pytest.mark.asyncio
async def test_generate_hypotheses_uses_fallback_when_llm_raises() -> None:
    llm = _FailingLLM()
    results, action, _, _ = await generate_hypotheses(
        assertions=[],
        source_claims=[],
        case_uid="case_test",
        llm=llm,  # type: ignore[arg-type]
        budget=BudgetContext(max_tokens=4096, max_cost_usd=1.0),
        context={"background_text": "cold-start"},
    )

    assert len(results) == 3
    assert action.outputs["fallback"] is True
