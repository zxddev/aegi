# Author: msq

from __future__ import annotations

from dataclasses import dataclass
import os


def _parse_csv_set(raw: str | None) -> set[str]:
    if not raw:
        return set()
    items: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            items.append(part.lower())
    return set(items)


@dataclass(frozen=True)
class Settings:
    allow_domains: set[str]
    min_interval_ms: int
    cache_enabled: bool
    cache_ttl_s: int
    searxng_base_url: str
    unstructured_base_url: str


def load_settings() -> Settings:
    allow_domains = _parse_csv_set(os.getenv("AEGI_GATEWAY_ALLOW_DOMAINS"))
    raw_min_interval = os.getenv("AEGI_GATEWAY_MIN_INTERVAL_MS", "0")
    try:
        min_interval_ms = int(raw_min_interval)
    except ValueError:
        min_interval_ms = 0

    if min_interval_ms < 0:
        min_interval_ms = 0

    raw_cache_enabled = os.getenv("AEGI_GATEWAY_CACHE_ENABLED", "0").strip().lower()
    cache_enabled = raw_cache_enabled in {"1", "true", "yes", "on"}

    raw_cache_ttl_s = os.getenv("AEGI_GATEWAY_CACHE_TTL_S", "60")
    try:
        cache_ttl_s = int(raw_cache_ttl_s)
    except ValueError:
        cache_ttl_s = 60
    if cache_ttl_s < 0:
        cache_ttl_s = 0

    return Settings(
        allow_domains=allow_domains,
        min_interval_ms=min_interval_ms,
        cache_enabled=cache_enabled,
        cache_ttl_s=cache_ttl_s,
        searxng_base_url=os.getenv("AEGI_SEARXNG_BASE_URL", "http://localhost:8701"),
        unstructured_base_url=os.getenv("AEGI_UNSTRUCTURED_BASE_URL", "http://localhost:8703"),
    )
