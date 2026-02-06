# Author: msq

from __future__ import annotations

from time import monotonic

from fastapi import APIRouter
from pydantic import BaseModel

from aegi_mcp_gateway.audit.tool_trace import record_tool_trace
from aegi_mcp_gateway.api.errors import invalid_url, policy_denied, rate_limited
from aegi_mcp_gateway.policy import evaluate_outbound_url
from aegi_mcp_gateway.settings import load_settings


router = APIRouter(prefix="/tools", tags=["tools"])


class MetaSearchRequest(BaseModel):
    q: str
    categories: list[str] | None = None
    language: str | None = None
    safesearch: int | None = None


@router.post("/meta_search")
async def meta_search(req: MetaSearchRequest) -> dict:
    # P0 (fixtures-only): stub contract, no live integrations.
    start = monotonic()
    settings = load_settings()
    response = {"ok": False, "tool": "meta_search", "error_code": "not_implemented", "q": req.q}
    record_tool_trace(
        {
            "tool_name": "meta_search",
            "request": req.model_dump(exclude_none=True),
            "response": response,
            "status": "not_implemented",
            "duration_ms": int((monotonic() - start) * 1000),
            "error": None,
            "policy": {
                "allowed": True,
                "reason": "no_outbound",
                "domain": None,
                "robots": {"checked": False, "allowed": None, "reason": "no_outbound"},
                "cache": {
                    "enabled": settings.cache_enabled,
                    "ttl_s": settings.cache_ttl_s,
                    "hit": False,
                },
            },
        }
    )
    return response


class ArchiveUrlRequest(BaseModel):
    url: str


@router.post("/archive_url")
async def archive_url(req: ArchiveUrlRequest) -> dict:
    # P0 (fixtures-only): stub contract, no live integrations.
    start = monotonic()
    settings = load_settings()
    decision = evaluate_outbound_url("archive_url", req.url, settings)

    if not decision.allowed:
        if decision.error_code == "invalid_url":
            exc = invalid_url({"url": req.url})
        elif decision.error_code == "rate_limited":
            exc = rate_limited({"url": req.url, "domain": decision.domain})
        else:
            exc = policy_denied(
                {"url": req.url, "domain": decision.domain, "reason": decision.reason}
            )

        error_response = {
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        }
        record_tool_trace(
            {
                "tool_name": "archive_url",
                "request": req.model_dump(exclude_none=True),
                "response": error_response,
                "status": "denied",
                "duration_ms": int((monotonic() - start) * 1000),
                "error": exc.error_code,
                "policy": {
                    "allowed": False,
                    "reason": decision.reason,
                    "domain": decision.domain,
                    "robots": decision.robots,
                    "cache": {
                        "enabled": settings.cache_enabled,
                        "ttl_s": settings.cache_ttl_s,
                        "hit": False,
                    },
                },
            }
        )
        raise exc

    response = {
        "ok": False,
        "tool": "archive_url",
        "error_code": "not_implemented",
        "url": req.url,
        "policy": {
            "allowed": True,
            "reason": decision.reason,
            "domain": decision.domain,
            "robots": decision.robots,
            "cache": {
                "enabled": settings.cache_enabled,
                "ttl_s": settings.cache_ttl_s,
                "hit": False,
            },
        },
    }
    record_tool_trace(
        {
            "tool_name": "archive_url",
            "request": req.model_dump(exclude_none=True),
            "response": response,
            "status": "not_implemented",
            "duration_ms": int((monotonic() - start) * 1000),
            "error": None,
            "policy": {
                "allowed": True,
                "reason": decision.reason,
                "domain": decision.domain,
                "robots": decision.robots,
                "cache": {
                    "enabled": settings.cache_enabled,
                    "ttl_s": settings.cache_ttl_s,
                    "hit": False,
                },
            },
        }
    )
    return response


class DocParseRequest(BaseModel):
    artifact_version_uid: str


@router.post("/doc_parse")
async def doc_parse(req: DocParseRequest) -> dict:
    # P0 (fixtures-only): stub contract, no live integrations.
    start = monotonic()
    settings = load_settings()
    response = {
        "ok": False,
        "tool": "doc_parse",
        "error_code": "not_implemented",
        "artifact_version_uid": req.artifact_version_uid,
    }
    record_tool_trace(
        {
            "tool_name": "doc_parse",
            "request": req.model_dump(exclude_none=True),
            "response": response,
            "status": "not_implemented",
            "duration_ms": int((monotonic() - start) * 1000),
            "error": None,
            "policy": {
                "allowed": True,
                "reason": "no_outbound",
                "domain": None,
                "robots": {"checked": False, "allowed": None, "reason": "no_outbound"},
                "cache": {
                    "enabled": settings.cache_enabled,
                    "ttl_s": settings.cache_ttl_s,
                    "hit": False,
                },
            },
        }
    )
    return response
