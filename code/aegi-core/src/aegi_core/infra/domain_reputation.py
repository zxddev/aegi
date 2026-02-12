# Author: msq
"""域名信誉画像库。

内置静态数据，不依赖外部 API。用于 source_credibility 多信号评分。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class DomainProfile:
    """域名信誉画像。"""

    domain: str
    base_score: float  # 0.0-1.0
    tier: str  # high | medium | low
    category: str  # wire_service | major_outlet | ...
    country: str  # ISO 2-letter
    domain_strengths: dict[str, float]
    notes: str = ""


def _tier_from_score(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def _strengths(base: dict[str, float], overrides: dict[str, float]) -> dict[str, float]:
    merged = dict(base)
    merged.update(overrides)
    return merged


_CATEGORY_STRENGTHS: dict[str, dict[str, float]] = {
    "wire_service": {
        "military": 0.85,
        "economy": 0.85,
        "politics": 0.88,
        "finance": 0.78,
        "defense_industry": 0.72,
    },
    "major_outlet": {
        "military": 0.75,
        "economy": 0.80,
        "politics": 0.82,
        "finance": 0.72,
        "defense_industry": 0.64,
    },
    "state_media": {
        "military": 0.68,
        "economy": 0.65,
        "politics": 0.80,
        "finance": 0.56,
        "defense_industry": 0.58,
    },
    "government": {
        "military": 0.80,
        "economy": 0.68,
        "politics": 0.78,
        "finance": 0.60,
        "defense_industry": 0.74,
    },
    "academic": {
        "military": 0.82,
        "economy": 0.82,
        "politics": 0.78,
        "finance": 0.76,
        "methodology": 0.90,
    },
    "industry": {
        "military": 0.88,
        "economy": 0.62,
        "politics": 0.66,
        "finance": 0.58,
        "defense_industry": 0.90,
    },
    "tabloid": {
        "military": 0.34,
        "economy": 0.34,
        "politics": 0.38,
        "finance": 0.30,
    },
    "blog": {
        "military": 0.45,
        "economy": 0.45,
        "politics": 0.48,
        "finance": 0.42,
    },
    "social_ugc": {
        "military": 0.34,
        "economy": 0.34,
        "politics": 0.36,
        "finance": 0.32,
        "user_generated": 0.30,
    },
}

_PROFILE_ROWS: tuple[tuple[str, float, str, str, dict[str, float], str], ...] = (
    # wire_service
    ("reuters.com", 0.95, "wire_service", "US", {"politics": 0.90}, ""),
    ("apnews.com", 0.94, "wire_service", "US", {"politics": 0.88}, ""),
    ("afp.com", 0.92, "wire_service", "FR", {}, ""),
    ("efe.com", 0.89, "wire_service", "ES", {}, ""),
    ("ansa.it", 0.88, "wire_service", "IT", {}, ""),
    ("dpa.com", 0.89, "wire_service", "DE", {}, ""),
    ("kyodonews.net", 0.88, "wire_service", "JP", {}, ""),
    ("yonhapnews.co.kr", 0.88, "wire_service", "KR", {}, ""),
    ("xinhua.com", 0.85, "wire_service", "CN", {"politics": 0.82}, ""),
    ("xinhuanet.com", 0.84, "wire_service", "CN", {"politics": 0.82}, ""),
    ("tass.com", 0.78, "wire_service", "RU", {"politics": 0.74}, ""),
    ("tass.ru", 0.76, "wire_service", "RU", {"politics": 0.72}, ""),
    ("interfax.ru", 0.75, "wire_service", "RU", {"politics": 0.72}, ""),
    ("aa.com.tr", 0.82, "wire_service", "TR", {}, ""),
    # major_outlet
    ("bbc.com", 0.90, "major_outlet", "GB", {"politics": 0.86}, ""),
    ("bbc.co.uk", 0.90, "major_outlet", "GB", {"politics": 0.86}, ""),
    ("cnn.com", 0.83, "major_outlet", "US", {}, ""),
    ("nytimes.com", 0.90, "major_outlet", "US", {"politics": 0.88}, ""),
    ("washingtonpost.com", 0.89, "major_outlet", "US", {"politics": 0.86}, ""),
    ("theguardian.com", 0.88, "major_outlet", "GB", {}, ""),
    ("ft.com", 0.90, "major_outlet", "GB", {"economy": 0.95, "finance": 0.95, "military": 0.60}, ""),
    ("economist.com", 0.90, "major_outlet", "GB", {"economy": 0.92}, ""),
    ("bloomberg.com", 0.90, "major_outlet", "US", {"economy": 0.94, "finance": 0.94, "military": 0.58}, ""),
    ("wsj.com", 0.89, "major_outlet", "US", {"economy": 0.92, "finance": 0.93}, ""),
    ("nbcnews.com", 0.84, "major_outlet", "US", {}, ""),
    ("cbsnews.com", 0.84, "major_outlet", "US", {}, ""),
    ("usatoday.com", 0.80, "major_outlet", "US", {}, ""),
    ("latimes.com", 0.82, "major_outlet", "US", {}, ""),
    ("npr.org", 0.86, "major_outlet", "US", {}, ""),
    ("time.com", 0.80, "major_outlet", "US", {}, ""),
    ("politico.com", 0.82, "major_outlet", "US", {"politics": 0.88}, ""),
    ("axios.com", 0.80, "major_outlet", "US", {}, ""),
    ("forbes.com", 0.78, "major_outlet", "US", {"economy": 0.88, "finance": 0.88}, ""),
    ("businessinsider.com", 0.75, "major_outlet", "US", {"economy": 0.84}, ""),
    ("aljazeera.com", 0.78, "major_outlet", "QA", {"politics": 0.84}, ""),
    ("dw.com", 0.84, "major_outlet", "DE", {}, ""),
    ("france24.com", 0.80, "major_outlet", "FR", {}, ""),
    ("nhk.or.jp", 0.82, "major_outlet", "JP", {}, ""),
    ("scmp.com", 0.80, "major_outlet", "HK", {"economy": 0.85}, ""),
    ("straitstimes.com", 0.82, "major_outlet", "SG", {}, ""),
    ("channelnewsasia.com", 0.81, "major_outlet", "SG", {}, ""),
    ("smh.com.au", 0.79, "major_outlet", "AU", {}, ""),
    ("theaustralian.com.au", 0.76, "major_outlet", "AU", {}, ""),
    ("globeandmail.com", 0.82, "major_outlet", "CA", {}, ""),
    ("cbc.ca", 0.83, "major_outlet", "CA", {}, ""),
    ("independent.co.uk", 0.76, "major_outlet", "GB", {}, ""),
    ("telegraph.co.uk", 0.79, "major_outlet", "GB", {}, ""),
    ("skynews.com", 0.78, "major_outlet", "GB", {}, ""),
    ("lemonde.fr", 0.84, "major_outlet", "FR", {}, ""),
    ("elpais.com", 0.80, "major_outlet", "ES", {}, ""),
    ("spiegel.de", 0.84, "major_outlet", "DE", {}, ""),
    ("faz.net", 0.82, "major_outlet", "DE", {}, ""),
    ("corriere.it", 0.78, "major_outlet", "IT", {}, ""),
    ("japantimes.co.jp", 0.79, "major_outlet", "JP", {}, ""),
    ("euronews.com", 0.76, "major_outlet", "FR", {}, ""),
    ("cna.com.tw", 0.80, "major_outlet", "TW", {}, ""),
    ("abcnews.go.com", 0.82, "major_outlet", "US", {}, ""),
    ("newsweek.com", 0.74, "major_outlet", "US", {}, ""),
    ("thehill.com", 0.73, "major_outlet", "US", {"politics": 0.80}, ""),
    ("huffpost.com", 0.72, "major_outlet", "US", {}, ""),
    # state_media
    ("people.com.cn", 0.79, "state_media", "CN", {"politics": 0.84}, ""),
    ("globaltimes.cn", 0.68, "state_media", "CN", {"politics": 0.82}, ""),
    ("chinadaily.com.cn", 0.77, "state_media", "CN", {}, ""),
    ("cgtn.com", 0.74, "state_media", "CN", {}, ""),
    ("cri.cn", 0.72, "state_media", "CN", {}, ""),
    ("sputniknews.com", 0.32, "state_media", "RU", {"politics": 0.40}, "state-aligned, mixed fact quality"),
    ("rt.com", 0.28, "state_media", "RU", {"politics": 0.38}, "controversial, high editorial bias"),
    ("presstv.ir", 0.45, "state_media", "IR", {}, ""),
    ("irna.ir", 0.66, "state_media", "IR", {}, ""),
    ("trtworld.com", 0.70, "state_media", "TR", {}, ""),
    ("ria.ru", 0.52, "state_media", "RU", {}, ""),
    ("pravda.ru", 0.25, "state_media", "RU", {"politics": 0.34}, "historically unreliable"),
    ("alalam.ir", 0.40, "state_media", "IR", {}, ""),
    ("huanqiu.com", 0.70, "state_media", "CN", {"politics": 0.82}, ""),
    # government
    ("state.gov", 0.84, "government", "US", {"politics": 0.82}, ""),
    ("defense.gov", 0.85, "government", "US", {"military": 0.90}, ""),
    ("whitehouse.gov", 0.80, "government", "US", {}, ""),
    ("gov.uk", 0.82, "government", "GB", {}, ""),
    ("mod.gov.cn", 0.82, "government", "CN", {"military": 0.88}, ""),
    ("mfa.gov.cn", 0.80, "government", "CN", {"politics": 0.84}, ""),
    ("nasa.gov", 0.83, "government", "US", {"technology": 0.90}, ""),
    ("europa.eu", 0.78, "government", "EU", {"politics": 0.82}, ""),
    ("army.mil", 0.82, "government", "US", {"military": 0.90}, ""),
    ("navy.mil", 0.82, "government", "US", {"military": 0.90}, ""),
    ("airforce.mil", 0.82, "government", "US", {"military": 0.90}, ""),
    ("mod.go.jp", 0.80, "government", "JP", {"military": 0.86}, ""),
    ("mofa.go.jp", 0.79, "government", "JP", {"politics": 0.84}, ""),
    # academic
    ("rand.org", 0.90, "academic", "US", {"military": 0.90, "methodology": 0.92}, ""),
    ("csis.org", 0.88, "academic", "US", {"military": 0.88}, ""),
    ("brookings.edu", 0.89, "academic", "US", {"economy": 0.88}, ""),
    ("iiss.org", 0.90, "academic", "GB", {"military": 0.92}, ""),
    ("cfr.org", 0.88, "academic", "US", {"politics": 0.86}, ""),
    ("carnegieendowment.org", 0.87, "academic", "US", {}, ""),
    ("sipri.org", 0.90, "academic", "SE", {"military": 0.92}, ""),
    ("chathamhouse.org", 0.87, "academic", "GB", {}, ""),
    ("wilsoncenter.org", 0.84, "academic", "US", {}, ""),
    ("atlanticcouncil.org", 0.83, "academic", "US", {}, ""),
    ("aspi.org.au", 0.82, "academic", "AU", {}, ""),
    ("merics.org", 0.82, "academic", "DE", {}, ""),
    ("lowyinstitute.org", 0.84, "academic", "AU", {}, ""),
    ("cnas.org", 0.84, "academic", "US", {"military": 0.86}, ""),
    ("understandingwar.org", 0.84, "academic", "US", {"military": 0.90}, ""),
    ("hoover.org", 0.80, "academic", "US", {}, ""),
    ("bruegel.org", 0.86, "academic", "BE", {"economy": 0.90}, ""),
    ("jamestown.org", 0.80, "academic", "US", {"military": 0.82}, ""),
    ("heritage.org", 0.72, "academic", "US", {"politics": 0.72}, ""),
    ("rusi.org", 0.85, "academic", "GB", {"military": 0.90}, ""),
    ("belfercenter.org", 0.84, "academic", "US", {"military": 0.84}, ""),
    ("csbaonline.org", 0.82, "academic", "US", {"military": 0.88}, ""),
    # industry
    (
        "janes.com",
        0.91,
        "industry",
        "GB",
        {"military": 0.95, "defense_industry": 0.95, "economy": 0.50},
        "",
    ),
    ("defensenews.com", 0.86, "industry", "US", {"military": 0.90}, ""),
    ("thediplomat.com", 0.83, "industry", "US", {"politics": 0.82}, ""),
    ("foreignaffairs.com", 0.88, "industry", "US", {"politics": 0.88}, ""),
    ("foreignpolicy.com", 0.84, "industry", "US", {"politics": 0.86}, ""),
    ("breakingdefense.com", 0.84, "industry", "US", {"defense_industry": 0.92}, ""),
    ("militarytimes.com", 0.80, "industry", "US", {"military": 0.88}, ""),
    ("warontherocks.com", 0.84, "industry", "US", {"military": 0.90}, ""),
    ("navalnews.com", 0.81, "industry", "FR", {"military": 0.88}, ""),
    ("aviationweek.com", 0.84, "industry", "US", {"defense_industry": 0.90}, ""),
    ("armyrecognition.com", 0.72, "industry", "BE", {"military": 0.84}, ""),
    ("thedefensepost.com", 0.78, "industry", "US", {"military": 0.84}, ""),
    ("defence-blog.com", 0.66, "industry", "PL", {"military": 0.78}, ""),
    ("19fortyfive.com", 0.62, "industry", "US", {"military": 0.75}, ""),
    ("smallwarsjournal.com", 0.76, "industry", "US", {"military": 0.82}, ""),
    ("nationalinterest.org", 0.72, "industry", "US", {"military": 0.76}, ""),
    ("c4isrnet.com", 0.78, "industry", "US", {"defense_industry": 0.88}, ""),
    ("navyrecognition.com", 0.74, "industry", "BE", {"military": 0.84}, ""),
    # tabloid
    ("dailymail.co.uk", 0.36, "tabloid", "GB", {}, ""),
    ("thesun.co.uk", 0.28, "tabloid", "GB", {}, ""),
    ("nypost.com", 0.42, "tabloid", "US", {}, ""),
    ("theblaze.com", 0.30, "tabloid", "US", {}, ""),
    ("gatewaypundit.com", 0.20, "tabloid", "US", {}, ""),
    ("zerohedge.com", 0.30, "tabloid", "US", {"economy": 0.45}, ""),
    ("oann.com", 0.25, "tabloid", "US", {}, ""),
    ("newsmax.com", 0.34, "tabloid", "US", {}, ""),
    ("dailycaller.com", 0.33, "tabloid", "US", {}, ""),
    ("mirror.co.uk", 0.40, "tabloid", "GB", {}, ""),
    ("express.co.uk", 0.33, "tabloid", "GB", {}, ""),
    ("rawstory.com", 0.45, "tabloid", "US", {}, ""),
    ("nationalenquirer.com", 0.18, "tabloid", "US", {}, ""),
    ("thestar.co.uk", 0.36, "tabloid", "GB", {}, ""),
    # blog
    ("medium.com", 0.55, "blog", "US", {}, ""),
    ("substack.com", 0.50, "blog", "US", {}, ""),
    ("blogspot.com", 0.42, "blog", "US", {}, ""),
    ("wordpress.com", 0.45, "blog", "US", {}, ""),
    ("tumblr.com", 0.40, "blog", "US", {}, ""),
    ("weebly.com", 0.38, "blog", "US", {}, ""),
    ("steemit.com", 0.35, "blog", "US", {}, ""),
    ("quora.com", 0.44, "blog", "US", {}, ""),
    ("rumble.com", 0.36, "blog", "US", {}, ""),
    ("patreon.com", 0.40, "blog", "US", {}, ""),
    ("ghost.io", 0.45, "blog", "US", {}, ""),
    ("livejournal.com", 0.34, "blog", "US", {}, ""),
    ("typepad.com", 0.35, "blog", "US", {}, ""),
    ("infowars.com", 0.12, "blog", "US", {}, "known conspiracy platform"),
    ("naturalnews.com", 0.12, "blog", "US", {}, "known misinformation platform"),
    ("breitbart.com", 0.18, "blog", "US", {}, "frequent factual controversies"),
    # social_ugc
    ("x.com", 0.36, "social_ugc", "US", {}, ""),
    ("twitter.com", 0.36, "social_ugc", "US", {}, ""),
    ("reddit.com", 0.38, "social_ugc", "US", {}, ""),
    ("facebook.com", 0.34, "social_ugc", "US", {}, ""),
    ("instagram.com", 0.33, "social_ugc", "US", {}, ""),
    ("youtube.com", 0.37, "social_ugc", "US", {}, ""),
    ("tiktok.com", 0.32, "social_ugc", "SG", {}, ""),
    ("weibo.com", 0.34, "social_ugc", "CN", {}, ""),
    ("telegram.org", 0.35, "social_ugc", "AE", {}, ""),
    ("vk.com", 0.30, "social_ugc", "RU", {}, ""),
    ("bilibili.com", 0.35, "social_ugc", "CN", {}, ""),
    ("douyin.com", 0.32, "social_ugc", "CN", {}, ""),
    ("mastodon.social", 0.37, "social_ugc", "DE", {}, ""),
    ("linkedin.com", 0.40, "social_ugc", "US", {}, ""),
    ("threads.net", 0.34, "social_ugc", "US", {}, ""),
    ("discord.com", 0.35, "social_ugc", "US", {}, ""),
)


def _build_profiles() -> Mapping[str, DomainProfile]:
    profiles: dict[str, DomainProfile] = {}
    for domain, score, category, country, overrides, notes in _PROFILE_ROWS:
        category_strengths = _CATEGORY_STRENGTHS.get(category, {})
        profiles[domain] = DomainProfile(
            domain=domain,
            base_score=score,
            tier=_tier_from_score(score),
            category=category,
            country=country,
            domain_strengths=_strengths(category_strengths, overrides),
            notes=notes,
        )
    return MappingProxyType(profiles)


DOMAIN_PROFILES: Mapping[str, DomainProfile] = _build_profiles()

_TLD_SCORES: Mapping[str, float] = MappingProxyType(
    {
        ".gov.cn": 0.80,
        ".gov.uk": 0.80,
        ".gov": 0.80,
        ".edu.cn": 0.75,
        ".ac.uk": 0.75,
        ".edu": 0.75,
        ".mil": 0.80,
        ".or.jp": 0.60,
        ".co.uk": 0.55,
        ".co.jp": 0.55,
        ".org": 0.55,
        ".eu": 0.60,
        ".com": 0.50,
        ".net": 0.45,
        ".info": 0.35,
        ".xyz": 0.25,
        ".tk": 0.15,
        ".ml": 0.15,
        ".ga": 0.15,
    }
)
_TLD_SUFFIXES = tuple(sorted(_TLD_SCORES.keys(), key=len, reverse=True))


def _normalize_domain(value: str) -> str:
    candidate = value.strip().lower()
    if "://" in candidate:
        parsed = urlparse(candidate)
        candidate = parsed.hostname or ""
    candidate = candidate.split(":", maxsplit=1)[0]
    if candidate.startswith("www."):
        candidate = candidate[4:]
    return candidate.strip(".")


@lru_cache(maxsize=2048)
def _domain_candidates(domain: str) -> tuple[str, ...]:
    labels = [label for label in domain.split(".") if label]
    if len(labels) <= 1:
        return (domain,)
    return tuple(".".join(labels[i:]) for i in range(len(labels) - 1))


def lookup_domain(domain: str) -> DomainProfile | None:
    """查找域名信誉，支持子域名回退。

    示例：news.bbc.co.uk -> bbc.co.uk。
    """

    normalized = _normalize_domain(domain)
    if not normalized:
        return None
    for candidate in _domain_candidates(normalized):
        profile = DOMAIN_PROFILES.get(candidate)
        if profile is not None:
            return profile
    return None


def lookup_tld(domain: str) -> tuple[float, str] | None:
    """按顶级域名推断信誉。"""

    normalized = _normalize_domain(domain)
    if not normalized:
        return None
    for suffix in _TLD_SUFFIXES:
        bare_suffix = suffix[1:]
        if normalized == bare_suffix or normalized.endswith(suffix):
            return _TLD_SCORES[suffix], suffix
    return None

