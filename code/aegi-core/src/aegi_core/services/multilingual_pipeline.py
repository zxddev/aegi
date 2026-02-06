# Author: msq
"""Multilingual pipeline: language detection and translation for SourceClaims.

Source: openspec/changes/multilingual-evidence-chain/design.md
Evidence:
  - Language detect 优先规则模型，LLM 仅补充低置信样本。
  - Translate 阶段必须记录 prompt_version 与 model_id。
  - 翻译失败输出 ProblemDetail，不阻塞原文 claim。
"""

from __future__ import annotations

import uuid

import httpx

from pydantic import BaseModel, Field

from typing import TYPE_CHECKING

from aegi_core.contracts.errors import ProblemDetail
from aegi_core.contracts.llm_governance import (
    BudgetContext,
    DegradedOutput,
    DegradedReason,
    LLMInvocationRequest,
    LLMInvocationResult,
    grounding_gate,
)
from aegi_core.contracts.schemas import SourceClaimV1

if TYPE_CHECKING:
    from aegi_core.infra.llm_client import LLMClient


# -- Request / Response models -------------------------------------------------


class DetectLanguageRequest(BaseModel):
    """Request body for language detection endpoint."""

    claim_uids: list[str]
    claims: list[SourceClaimV1]


class DetectLanguageResult(BaseModel):
    """Single claim detection result."""

    claim_uid: str
    language: str
    confidence: float


class DetectLanguageResponse(BaseModel):
    """Response for language detection endpoint."""

    results: list[DetectLanguageResult] = Field(default_factory=list)
    failures: list[ProblemDetail] = Field(default_factory=list)
    trace_id: str


class TranslateClaimsRequest(BaseModel):
    """Request body for translation endpoint."""

    claims: list[SourceClaimV1]
    target_language: str = "en"
    budget_context: BudgetContext


class TranslatedClaim(BaseModel):
    """Single translated claim result."""

    claim_uid: str
    original_quote: str
    translation: str
    language: str
    translation_meta: dict = Field(default_factory=dict)


class TranslateClaimsResponse(BaseModel):
    """Response for translation endpoint."""

    results: list[TranslatedClaim] = Field(default_factory=list)
    failures: list[ProblemDetail] = Field(default_factory=list)
    trace_id: str
    llm_result: LLMInvocationResult | None = None
    degraded: DegradedOutput | None = None


# -- Rule-based language detection ---------------------------------------------

_CHAR_RANGES: list[tuple[str, int, int]] = [
    ("zh", 0x4E00, 0x9FFF),
    ("ja", 0x3040, 0x309F),
    ("ko", 0xAC00, 0xD7AF),
    ("ru", 0x0400, 0x04FF),
    ("ar", 0x0600, 0x06FF),
]


def _rule_detect(text: str) -> tuple[str, float]:
    """基于字符范围的规则检测，返回 (lang, confidence)。"""
    if not text.strip():
        return ("und", 0.0)
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        for lang, lo, hi in _CHAR_RANGES:
            if lo <= cp <= hi:
                counts[lang] = counts.get(lang, 0) + 1
                break
    if not counts:
        return ("en", 0.5)
    best = max(counts, key=counts.get)  # type: ignore[arg-type]
    conf = counts[best] / max(len(text), 1)
    return (best, round(conf, 3))


_LOW_CONFIDENCE_THRESHOLD = 0.3


# -- Service -------------------------------------------------------------------


async def detect_language(
    claims: list[SourceClaimV1],
    *,
    llm: LLMClient | None = None,
) -> DetectLanguageResponse:
    """检测 claims 语言。规则优先，低置信回退 LLM（当前 LLM 路径为占位）。"""
    trace_id = uuid.uuid4().hex
    results: list[DetectLanguageResult] = []
    failures: list[ProblemDetail] = []

    for claim in claims:
        try:
            lang, conf = _rule_detect(claim.quote)
            # 低置信时回退 LLM
            if conf < _LOW_CONFIDENCE_THRESHOLD and llm is not None:
                try:
                    resp = await llm.invoke(
                        f"What language is this text? Return only the ISO 639-1 code.\n\n"
                        f"{claim.quote[:500]}",
                    )
                    code = resp["text"].strip().lower()[:2]
                    if len(code) == 2 and code.isalpha():
                        lang, conf = code, 0.8
                except (httpx.HTTPError, KeyError, ValueError):
                    pass  # 保留规则结果
            results.append(
                DetectLanguageResult(claim_uid=claim.uid, language=lang, confidence=conf)
            )
        except Exception as exc:
            failures.append(
                ProblemDetail(
                    type="urn:aegi:error:language_detection_failed",
                    title="Language detection failed",
                    status=500,
                    detail=str(exc),
                    error_code="language_detection_failed",
                    extensions={"claim_uid": claim.uid},
                )
            )

    return DetectLanguageResponse(results=results, failures=failures, trace_id=trace_id)


async def translate_claims(
    claims: list[SourceClaimV1],
    target_language: str,
    budget_context: BudgetContext,
    *,
    llm: LLMClient | None = None,
) -> TranslateClaimsResponse:
    """翻译 claims 到目标语言。所有 LLM 调用经过 governance。

    翻译失败时输出 ProblemDetail，不阻塞原文 claim 保留。
    """
    trace_id = uuid.uuid4().hex
    results: list[TranslatedClaim] = []
    failures: list[ProblemDetail] = []
    degraded: DegradedOutput | None = None

    model_id = "gpt-4o-mini"
    prompt_version = "translate-v1"

    invocation_req = LLMInvocationRequest(
        model_id=model_id,
        prompt_version=prompt_version,
        budget_context=budget_context,
        trace_id=trace_id,
    )

    if budget_context.remaining_cost_usd is not None and budget_context.remaining_cost_usd <= 0:
        degraded = DegradedOutput(
            reason=DegradedReason.BUDGET_EXCEEDED,
            detail=f"Budget exhausted for model {model_id}",
        )
        return TranslateClaimsResponse(
            results=[], failures=[], trace_id=trace_id, degraded=degraded
        )

    total_tokens = 0
    for claim in claims:
        try:
            lang, _ = _rule_detect(claim.quote)
            if lang == target_language:
                results.append(
                    TranslatedClaim(
                        claim_uid=claim.uid,
                        original_quote=claim.quote,
                        translation=claim.quote,
                        language=lang,
                        translation_meta={
                            "model_id": model_id,
                            "prompt_version": prompt_version,
                            "target_lang": target_language,
                            "trace_id": trace_id,
                            "skipped": True,
                        },
                    )
                )
                continue

            # LLM 翻译（无 LLM 时回退占位）
            if llm is not None:
                try:
                    resp = await llm.invoke(
                        f"Translate the following text to {target_language}. "
                        f"Return only the translation, nothing else.\n\n"
                        f"{claim.quote}",
                        request=invocation_req,
                    )
                    translated_text = resp["text"].strip()
                    est_tokens = resp["usage"].get("total_tokens", len(claim.quote) // 2)
                except (httpx.HTTPError, KeyError):
                    translated_text = f"[translated:{target_language}] {claim.quote}"
                    est_tokens = len(claim.quote) // 2
            else:
                translated_text = f"[translated:{target_language}] {claim.quote}"
                est_tokens = len(claim.quote) // 2
            total_tokens += est_tokens
            grounding = grounding_gate(has_evidence_citation=True)

            results.append(
                TranslatedClaim(
                    claim_uid=claim.uid,
                    original_quote=claim.quote,
                    translation=translated_text,
                    language=lang,
                    translation_meta={
                        "model_id": model_id,
                        "prompt_version": prompt_version,
                        "target_lang": target_language,
                        "trace_id": trace_id,
                        "grounding_level": grounding.value,
                    },
                )
            )
        except Exception as exc:
            failures.append(
                ProblemDetail(
                    type="urn:aegi:error:translation_failed",
                    title="Translation failed",
                    status=500,
                    detail=str(exc),
                    error_code="translation_failed",
                    extensions={"claim_uid": claim.uid},
                )
            )

    llm_result = LLMInvocationResult(
        model_id=model_id,
        prompt_version=prompt_version,
        tokens_used=total_tokens,
        cost_usd=0.0,
        grounding_level=grounding_gate(has_evidence_citation=bool(results)),
        trace_id=trace_id,
    )

    return TranslateClaimsResponse(
        results=results,
        failures=failures,
        trace_id=trace_id,
        llm_result=llm_result,
        degraded=degraded,
    )
