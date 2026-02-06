# Author: msq

from __future__ import annotations


class GatewayHTTPError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str, details: dict) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details


def policy_denied(details: dict) -> GatewayHTTPError:
    return GatewayHTTPError(403, "policy_denied", "Policy denied request", details)


def invalid_url(details: dict) -> GatewayHTTPError:
    return GatewayHTTPError(400, "invalid_url", "Invalid URL", details)


def rate_limited(details: dict) -> GatewayHTTPError:
    return GatewayHTTPError(429, "rate_limited", "Rate limited", details)
