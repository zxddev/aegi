"""来源可信度评分测试 — 基于规则的域名信誉。"""

from aegi_core.services.source_credibility import score_domain


def test_high_credibility_reuters():
    result = score_domain("https://www.reuters.com/article/some-news")
    assert result.domain == "reuters.com"
    assert result.score == 0.9
    assert result.tier == "high"
    assert "wire service" in result.reason or "major outlet" in result.reason


def test_gov_domain():
    result = score_domain("https://www.state.gov/reports/2025")
    assert result.domain == "state.gov"
    assert result.score == 0.8
    assert result.tier == "medium"
    assert ".gov" in result.reason


def test_edu_domain():
    result = score_domain("https://cs.stanford.edu/research/paper.html")
    assert result.domain == "cs.stanford.edu"
    assert result.score == 0.8
    assert result.tier == "medium"
    assert ".edu" in result.reason


def test_unknown_domain():
    result = score_domain("https://random.xyz/page")
    assert result.domain == "random.xyz"
    assert result.score == 0.5
    assert result.tier == "unknown"
    assert "unrecognized" in result.reason


def test_low_credibility():
    result = score_domain("https://infowars.com/article/123")
    assert result.domain == "infowars.com"
    assert result.score == 0.2
    assert result.tier == "low"
    assert "low-credibility" in result.reason
