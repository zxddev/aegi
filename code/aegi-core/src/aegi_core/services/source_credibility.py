# Author: msq
"""Source credibility scoring based on deterministic multi-signal rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from aegi_core.infra.domain_reputation import lookup_domain, lookup_tld

_DEFAULT_UNKNOWN_DOMAIN_SCORE = 0.45
_DEFAULT_UNKNOWN_TLD_SCORE = 0.50

_WEIGHTS_WITH_CONTENT: dict[str, float] = {
    "domain_reputation": 0.50,
    "tld_trust": 0.15,
    "content_quality": 0.20,
    "url_heuristics": 0.15,
}
_WEIGHTS_NO_CONTENT: dict[str, float] = {
    "domain_reputation": 0.60,
    "tld_trust": 0.20,
    "url_heuristics": 0.20,
}

_NUMBER_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?\b")
_DATE_PATTERN = re.compile(
    r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
_WORD_PATTERN = re.compile(r"[A-Za-z0-9_]+")
_CJK_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")

_REPORTING_PHRASES = (
    "according to",
    "sources said",
    "said",
    "reported",
    "stated",
    "spokesperson",
    "official",
    "ministry",
    "department",
    "据",
    "报道称",
    "表示",
)
_ATTRIBUTION_PHRASES = (
    "according to",
    "report by",
    "statement from",
    "told reporters",
    "said the ministry",
    "said a spokesperson",
    "根据",
    "消息人士",
)
_SENSATIONAL_TERMS = (
    "shocking",
    "breaking",
    "you won't believe",
    "must see",
    "exclusive truth",
    "exposed",
    "绝对想不到",
    "震惊",
    "劲爆",
)
_SUSPICIOUS_PATH_SEGMENTS = (
    "/sponsored/",
    "/partner/",
    "/advertorial/",
    "/promoted/",
    "/clickbait/",
)

_CONTEXT_ALIASES = {
    "defence": "defense_industry",
    "defense": "defense_industry",
    "security": "military",
    "geopolitics": "politics",
    "macro": "economy",
}


@dataclass
class CredibilityScore:
    domain: str
    score: float  # 0.0 - 1.0
    tier: str  # high | medium | low | unknown
    reason: str
    domain_scores: dict[str, float] | None = None
    signals: dict[str, float] | None = None
    conflict_discount: float = 1.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _extract_domain(url: str) -> str:
    """Extract a normalized host from URL."""

    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    host = (parsed.hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _canonical_context(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return _CONTEXT_ALIASES.get(normalized, normalized)


def _score_to_tier(score: float, *, known_domain: bool) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    if score < 0.35:
        return "low"
    return "low" if known_domain else "unknown"


def _estimate_word_count(text: str) -> int:
    latin_tokens = len(_WORD_PATTERN.findall(text))
    cjk_tokens = len(_CJK_CHAR_PATTERN.findall(text)) // 2
    return latin_tokens + cjk_tokens


def _score_content_quality(content: str) -> float:
    """Score article quality with deterministic heuristics (no LLM)."""

    text = content.strip()
    if not text:
        return 0.35

    lower = text.lower()
    first_line = next((line for line in text.splitlines() if line.strip()), text[:120])
    word_count = _estimate_word_count(text)
    score = 0.50

    has_quote = bool(re.search(r"\".{8,}\"|“.{8,}”", text))
    has_reporting = any(phrase in lower for phrase in _REPORTING_PHRASES)
    if has_quote or has_reporting:
        score += 0.12

    if _NUMBER_PATTERN.search(text):
        score += 0.07
    if _DATE_PATTERN.search(lower):
        score += 0.05

    paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    if len(paragraphs) >= 3:
        score += 0.06

    if any(phrase in lower for phrase in _ATTRIBUTION_PHRASES):
        score += 0.06

    letters = [ch for ch in first_line if ch.isalpha()]
    if len(letters) >= 10:
        uppercase_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
        if uppercase_ratio > 0.8:
            score -= 0.12

    exclamation_count = text.count("!")
    if exclamation_count:
        score -= min(0.18, exclamation_count * 0.03)

    sensational_hits = sum(lower.count(term) for term in _SENSATIONAL_TERMS)
    if sensational_hits:
        density = sensational_hits / max(word_count, 1)
        score -= min(0.24, 0.08 + density * 3.5)

    if word_count < 100:
        score -= 0.20
    elif word_count < 180:
        score -= 0.08

    return _clamp(score)


def _score_url_heuristics(url: str) -> float:
    """Score URL quality with structural heuristics."""

    try:
        parsed = urlparse(url)
    except ValueError:
        return 0.2

    host = (parsed.hostname or "").lower()
    if not host:
        return 0.2
    if host.startswith("www."):
        host = host[4:]

    score = 0.62
    path = (parsed.path or "").lower()
    depth = len([segment for segment in path.split("/") if segment])
    params = parse_qs(parsed.query, keep_blank_values=True)
    param_count = len(params)

    if depth <= 3:
        score += 0.08
    if depth > 5:
        score -= min(0.22, 0.10 + 0.03 * (depth - 5))

    if param_count >= 4:
        score -= min(0.20, 0.10 + 0.02 * (param_count - 3))
    elif param_count >= 2:
        score -= 0.05

    if any(pattern in path for pattern in _SUSPICIOUS_PATH_SEGMENTS):
        score -= 0.20

    if re.search(r"\d", host):
        score -= 0.08
    if len(host) > 30:
        score -= 0.08
    if host.count("-") >= 3:
        score -= 0.05
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        score -= 0.15
    if not parsed.query and depth <= 3:
        score += 0.05

    return _clamp(score)


def _weighted_score(signals: dict[str, float], weights: dict[str, float]) -> float:
    return sum(signals[key] * weight for key, weight in weights.items())


def get_contextual_score(credibility: CredibilityScore, domain_context: str) -> float:
    """Return context-adjusted score when domain-strength data exists."""

    context_key = _canonical_context(domain_context)
    if not credibility.domain_scores:
        return credibility.score
    if context_key not in credibility.domain_scores:
        return credibility.score
    return _clamp(credibility.domain_scores[context_key])


def score_source(
    url: str,
    *,
    content: str | None = None,
    domain_context: str | None = None,
) -> CredibilityScore:
    """Score source credibility with multiple deterministic signals.

    Weights with content:
      - domain_reputation: 0.50
      - tld_trust: 0.15
      - content_quality: 0.20
      - url_heuristics: 0.15

    Weights without content:
      - domain_reputation: 0.60
      - tld_trust: 0.20
      - url_heuristics: 0.20
    """

    domain = _extract_domain(url)
    if not domain:
        return CredibilityScore(
            domain="",
            score=0.3,
            tier="unknown",
            reason="invalid URL",
            signals={"domain_reputation": 0.3, "tld_trust": 0.3, "url_heuristics": 0.3},
        )

    profile = lookup_domain(domain)
    tld_info = lookup_tld(domain)
    tld_score = tld_info[0] if tld_info else _DEFAULT_UNKNOWN_TLD_SCORE
    url_score = _score_url_heuristics(url)
    domain_reputation_score = profile.base_score if profile else _DEFAULT_UNKNOWN_DOMAIN_SCORE

    has_content = bool(content and content.strip())
    weights = _WEIGHTS_WITH_CONTENT if has_content else _WEIGHTS_NO_CONTENT
    signals: dict[str, float] = {
        "domain_reputation": domain_reputation_score,
        "tld_trust": tld_score,
        "url_heuristics": url_score,
    }
    if has_content and content is not None:
        signals["content_quality"] = _score_content_quality(content)

    score = _weighted_score(signals, weights)

    # Keep known low-credibility sources from being inflated by clean URL structure.
    if profile and profile.tier == "low":
        score *= 0.9

    domain_scores = dict(profile.domain_strengths) if profile else None
    conflict_discount = 1.0
    if domain_context:
        contextual_score = get_contextual_score(
            CredibilityScore(
                domain=domain,
                score=score,
                tier="unknown",
                reason="",
                domain_scores=domain_scores,
            ),
            domain_context,
        )
        if contextual_score < score:
            conflict_discount = _clamp(contextual_score / max(score, 1e-6))
            score = contextual_score

    score = _clamp(score)
    tier = _score_to_tier(score, known_domain=profile is not None)
    rounded_signals = {key: round(value, 4) for key, value in signals.items()}

    reason_parts = []
    if profile:
        reason_parts.append(
            f"domain profile: {profile.domain} ({profile.category}/{profile.tier})"
        )
    else:
        reason_parts.append("domain profile: unknown")
    reason_parts.append(f"tld trust: {tld_info[1] if tld_info else 'default'}")
    reason_parts.append("content quality: on" if has_content else "content quality: off")
    if domain_context and conflict_discount < 1.0:
        reason_parts.append(
            f"contextual discount: {domain_context} x{conflict_discount:.2f}"
        )
    if profile and profile.notes:
        reason_parts.append(f"note: {profile.notes}")

    return CredibilityScore(
        domain=domain,
        score=round(score, 4),
        tier=tier,
        reason="; ".join(reason_parts),
        domain_scores=domain_scores,
        signals=rounded_signals,
        conflict_discount=round(conflict_discount, 4),
    )


def score_domain(url: str) -> CredibilityScore:
    """Backward-compatible API for existing callers."""

    return score_source(url)

