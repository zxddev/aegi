# Author: msq
"""Tests for multilingual pipeline: language detection and translation.

Source: openspec/changes/multilingual-evidence-chain/tasks.md (task 4.2)
Evidence: 翻译失败输出结构化错误，不阻塞原文 claim 保留。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aegi_core.contracts.llm_governance import BudgetContext
from aegi_core.contracts.schemas import SourceClaimV1
from aegi_core.services.multilingual_pipeline import (
    DetectLanguageResponse,
    TranslateClaimsResponse,
    detect_language,
    translate_claims,
)


def _make_claim(uid: str, quote: str) -> SourceClaimV1:
    return SourceClaimV1(
        uid=uid,
        case_uid="case-1",
        artifact_version_uid="av-1",
        chunk_uid="ch-1",
        evidence_uid="ev-1",
        quote=quote,
        created_at=datetime.now(timezone.utc),
    )


def _budget() -> BudgetContext:
    return BudgetContext(max_tokens=1000, max_cost_usd=1.0, remaining_cost_usd=1.0)


@pytest.mark.asyncio
async def test_detect_chinese() -> None:
    resp = await detect_language([_make_claim("c1", "中国是一个大国")])
    assert isinstance(resp, DetectLanguageResponse)
    assert resp.results[0].language == "zh"
    assert resp.results[0].confidence > 0
    assert resp.trace_id


@pytest.mark.asyncio
async def test_detect_english() -> None:
    resp = await detect_language([_make_claim("c2", "The quick brown fox")])
    assert resp.results[0].language == "en"


@pytest.mark.asyncio
async def test_detect_russian() -> None:
    resp = await detect_language([_make_claim("c3", "Россия — большая страна")])
    assert resp.results[0].language == "ru"


@pytest.mark.asyncio
async def test_detect_empty_quote() -> None:
    resp = await detect_language([_make_claim("c4", "")])
    assert resp.results[0].language == "und"
    assert resp.results[0].confidence == 0.0


@pytest.mark.asyncio
async def test_detect_multiple_claims() -> None:
    claims = [_make_claim("c5", "中文文本"), _make_claim("c6", "English text")]
    resp = await detect_language(claims)
    assert len(resp.results) == 2
    assert resp.failures == []


@pytest.mark.asyncio
async def test_translate_basic() -> None:
    resp = await translate_claims(
        [_make_claim("c1", "中国是一个大国")], "en", _budget()
    )
    assert isinstance(resp, TranslateClaimsResponse)
    r = resp.results[0]
    assert r.original_quote == "中国是一个大国"
    assert r.translation
    assert r.translation_meta["model_id"]
    assert r.translation_meta["prompt_version"]
    assert r.translation_meta["target_lang"] == "en"
    assert resp.degraded is None


@pytest.mark.asyncio
async def test_translate_same_language_skipped() -> None:
    resp = await translate_claims([_make_claim("c2", "Hello world")], "en", _budget())
    assert resp.results[0].translation_meta.get("skipped") is True


@pytest.mark.asyncio
async def test_translate_budget_exceeded() -> None:
    budget = BudgetContext(max_tokens=0, max_cost_usd=0.0, remaining_cost_usd=0.0)
    resp = await translate_claims([_make_claim("c3", "中文")], "en", budget)
    assert resp.degraded is not None
    assert resp.degraded.reason.value == "budget_exceeded"
    assert resp.results == []


@pytest.mark.asyncio
async def test_translate_preserves_original_quote() -> None:
    """验证 original_quote 保真（spec acceptance 5.2）。"""
    original = "Россия — большая страна"
    resp = await translate_claims([_make_claim("c4", original)], "en", _budget())
    assert resp.results[0].original_quote == original


@pytest.mark.asyncio
async def test_translate_llm_result_audit() -> None:
    """验证 LLM 调用审计信息完整。"""
    resp = await translate_claims([_make_claim("c5", "中文文本")], "en", _budget())
    assert resp.llm_result is not None
    assert resp.llm_result.model_id
    assert resp.llm_result.prompt_version
    assert resp.llm_result.trace_id == resp.trace_id
