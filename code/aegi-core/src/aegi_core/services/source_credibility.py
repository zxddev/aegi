"""来源可信度评分 — 基于规则的域名信誉打分。

不需要 LLM。评分结果附加到 ArtifactVersion.source_meta。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class CredibilityScore:
    domain: str
    score: float  # 0.0 - 1.0
    tier: str  # high | medium | low | unknown
    reason: str


# 已知高可信度通讯社/主流媒体
_HIGH_DOMAINS: set[str] = {
    "reuters.com",
    "apnews.com",
    "afp.com",
    "bbc.com",
    "bbc.co.uk",
    "nytimes.com",
    "washingtonpost.com",
    "theguardian.com",
    "economist.com",
    "ft.com",
    "bloomberg.com",
    "xinhuanet.com",
    "chinadaily.com.cn",
}

# 已知中等可信度的顶级域名
_MEDIUM_TLDS: set[str] = {".gov", ".edu", ".mil", ".ac.uk", ".gov.cn", ".edu.cn"}

# 已知低可信度/小报域名
_LOW_DOMAINS: set[str] = {
    "infowars.com",
    "naturalnews.com",
    "breitbart.com",
}


def _extract_domain(url: str) -> str:
    """从 URL 中提取可注册域名。"""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # 去掉 www. 前缀
        if host.startswith("www."):
            host = host[4:]
        return host.lower()
    except Exception:
        return ""


def score_domain(url: str) -> CredibilityScore:
    """根据域名信誉为 URL 打可信度分。"""
    domain = _extract_domain(url)
    if not domain:
        return CredibilityScore(
            domain="", score=0.3, tier="unknown", reason="invalid URL"
        )

    # 检查高可信度域名
    for hd in _HIGH_DOMAINS:
        if domain == hd or domain.endswith(f".{hd}"):
            return CredibilityScore(
                domain=domain,
                score=0.9,
                tier="high",
                reason=f"known wire service / major outlet: {hd}",
            )

    # 检查低可信度域名
    for ld in _LOW_DOMAINS:
        if domain == ld or domain.endswith(f".{ld}"):
            return CredibilityScore(
                domain=domain,
                score=0.2,
                tier="low",
                reason=f"known low-credibility source: {ld}",
            )

    # 检查中等可信度顶级域名
    for tld in _MEDIUM_TLDS:
        if domain.endswith(tld):
            return CredibilityScore(
                domain=domain,
                score=0.8,
                tier="medium",
                reason=f"institutional TLD: {tld}",
            )

    # 默认：未知
    return CredibilityScore(
        domain=domain,
        score=0.5,
        tier="unknown",
        reason="unrecognized domain",
    )
