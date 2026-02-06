# Author: msq

from __future__ import annotations

from dataclasses import dataclass
import time
from urllib.parse import urlparse

from aegi_mcp_gateway.settings import Settings


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    error_code: str | None
    reason: str
    domain: str | None
    robots: dict


_LAST_CALL_MONO: dict[str, float] = {}


def _robots_metadata() -> dict:
    # P0 (fixtures-only): no live robots/ToS enforcement, but we still record the decision metadata.
    return {
        "checked": False,
        "allowed": None,
        "reason": "p0_fixtures_only",
    }


def evaluate_outbound_url(tool_name: str, url: str, settings: Settings) -> PolicyDecision:
    parsed = urlparse(url)
    domain = parsed.hostname.lower() if parsed.hostname else None
    if not domain:
        return PolicyDecision(
            allowed=False,
            error_code="invalid_url",
            reason="missing_hostname",
            domain=None,
            robots=_robots_metadata(),
        )

    if domain not in settings.allow_domains:
        return PolicyDecision(
            allowed=False,
            error_code="policy_denied",
            reason="domain_not_allowed",
            domain=domain,
            robots=_robots_metadata(),
        )

    if settings.min_interval_ms > 0:
        now = time.monotonic()
        key = f"{tool_name}:{domain}"
        last = _LAST_CALL_MONO.get(key)
        if last is not None:
            elapsed_ms = (now - last) * 1000
            if elapsed_ms < settings.min_interval_ms:
                return PolicyDecision(
                    allowed=False,
                    error_code="rate_limited",
                    reason="min_interval_not_elapsed",
                    domain=domain,
                    robots=_robots_metadata(),
                )
        _LAST_CALL_MONO[key] = now

    return PolicyDecision(
        allowed=True,
        error_code=None,
        reason="allowed",
        domain=domain,
        robots=_robots_metadata(),
    )
