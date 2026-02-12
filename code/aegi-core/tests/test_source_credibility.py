# Author: msq
"""Tests for multi-signal source credibility scoring."""

from aegi_core.infra.domain_reputation import DOMAIN_PROFILES
from aegi_core.services.source_credibility import (
    CredibilityScore,
    score_domain,
    score_source,
)


def test_known_high_credibility_domains() -> None:
    result_reuters = score_source("https://www.reuters.com/world/sample")
    result_ap = score_source("https://apnews.com/article/sample")
    assert result_reuters.tier == "high"
    assert result_ap.tier == "high"
    assert result_reuters.score > 0.8
    assert result_ap.score > 0.8


def test_known_low_credibility_domains() -> None:
    infowars = score_source("https://infowars.com/article/123")
    naturalnews = score_source("https://naturalnews.com/health/story")
    assert infowars.tier == "low"
    assert naturalnews.tier == "low"
    assert infowars.score < 0.3
    assert naturalnews.score < 0.3


def test_government_tld() -> None:
    result = score_source("https://updates.someunit.mil/briefing")
    assert result.score >= 0.55
    assert result.tier in {"high", "medium"}


def test_unknown_domain_not_050() -> None:
    result = score_source("https://random.xyz/page")
    assert result.domain == "random.xyz"
    assert result.score != 0.5
    assert result.tier in {"unknown", "low", "medium"}


def test_subdomain_fallback() -> None:
    result = score_source("https://news.bbc.co.uk/world/story")
    assert result.domain == "news.bbc.co.uk"
    assert "bbc.co.uk" in result.reason
    assert result.score > 0.7


def test_content_quality_with_citations() -> None:
    high_quality = """
    According to the defense ministry, 12 aircraft were deployed on 2026-01-05.
    A spokesperson said the operation was limited and recorded in official logs.

    The report by the parliamentary committee cited two prior incidents and
    included 38 pages of supporting evidence.
    """
    low_quality = "BREAKING!!! shocking truth!!!"

    high = score_source("https://example.com/news/analysis", content=high_quality)
    low = score_source("https://example.com/news/analysis", content=low_quality)
    assert high.signals is not None
    assert low.signals is not None
    assert high.signals["content_quality"] > low.signals["content_quality"]
    assert high.score > low.score


def test_content_quality_sensationalism() -> None:
    neutral = "Officials stated that the policy update will be reviewed next month."
    sensational = "SHOCKING BREAKING NEWS!!! YOU WON'T BELIEVE THIS!!!"

    neutral_score = score_source("https://example.com/topic", content=neutral)
    sensational_score = score_source("https://example.com/topic", content=sensational)
    assert neutral_score.signals is not None
    assert sensational_score.signals is not None
    assert neutral_score.signals["content_quality"] > sensational_score.signals["content_quality"]


def test_url_heuristics_suspicious() -> None:
    clean = score_source("https://example.com/world/briefing")
    suspicious = score_source(
        "https://news123-very-long-host-name-example-domain.com/"
        "sponsored/partner/advertorial/deep/path/segment"
        "?utm_source=a&utm_campaign=b&utm_medium=c&utm_term=d"
    )
    assert clean.signals is not None
    assert suspicious.signals is not None
    assert clean.signals["url_heuristics"] > suspicious.signals["url_heuristics"]


def test_contextual_military_domain() -> None:
    military = score_source(
        "https://www.janes.com/defence-news/sample",
        domain_context="military",
    )
    economy = score_source(
        "https://www.janes.com/defence-news/sample",
        domain_context="economy",
    )
    assert military.score > economy.score
    assert economy.conflict_discount < 1.0


def test_contextual_finance_domain() -> None:
    economy = score_source("https://www.ft.com/content/sample", domain_context="economy")
    military = score_source("https://www.ft.com/content/sample", domain_context="military")
    assert economy.score > military.score


def test_contextual_no_domain_data() -> None:
    base = score_source("https://unknown-example-domain-abc.com/story")
    contextual = score_source(
        "https://unknown-example-domain-abc.com/story",
        domain_context="military",
    )
    assert base.score == contextual.score


def test_domain_reputation_coverage() -> None:
    assert len(DOMAIN_PROFILES) >= 100


def test_domain_reputation_categories() -> None:
    expected_categories = {
        "wire_service",
        "major_outlet",
        "state_media",
        "government",
        "academic",
        "industry",
        "tabloid",
        "blog",
        "social_ugc",
    }
    categories = {profile.category for profile in DOMAIN_PROFILES.values()}
    assert expected_categories.issubset(categories)


def test_backward_compatible_api() -> None:
    result = score_domain("https://www.reuters.com/world/sample")
    assert isinstance(result, CredibilityScore)
    assert result.domain == "reuters.com"
