# Author: msq

from __future__ import annotations

from time import monotonic

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from aegi_mcp_gateway.api.errors import invalid_url, policy_denied, rate_limited
from aegi_mcp_gateway.audit.tool_trace import record_tool_trace
from aegi_mcp_gateway.policy import evaluate_outbound_url
from aegi_mcp_gateway.settings import load_settings


router = APIRouter(prefix="/tools", tags=["tools"])

_HTTP_TIMEOUT = 15.0


# ── helpers ──────────────────────────────────────────────────────


def _policy_block(settings, *, tool_name: str) -> dict:
    return {
        "allowed": True,
        "reason": "no_outbound",
        "domain": None,
        "robots": {"checked": False, "allowed": None, "reason": "no_outbound"},
        "cache": {
            "enabled": settings.cache_enabled,
            "ttl_s": settings.cache_ttl_s,
            "hit": False,
        },
    }


def _trace(
    *,
    tool_name: str,
    request: dict,
    response: dict,
    status: str,
    duration_ms: int,
    error: str | None,
    policy: dict,
) -> None:
    record_tool_trace(
        {
            "tool_name": tool_name,
            "request": request,
            "response": response,
            "status": status,
            "duration_ms": duration_ms,
            "error": error,
            "policy": policy,
        }
    )


# ── meta_search ──────────────────────────────────────────────────


class MetaSearchRequest(BaseModel):
    q: str
    categories: list[str] | None = None
    language: str | None = None
    safesearch: int | None = None


@router.post("/meta_search")
async def meta_search(req: MetaSearchRequest) -> dict:
    """元搜索：当前无后端，返回空结果（降级模式）。"""
    start = monotonic()
    settings = load_settings()
    policy = _policy_block(settings, tool_name="meta_search")
    response = {"ok": True, "tool": "meta_search", "results": [], "q": req.q}
    _trace(
        tool_name="meta_search",
        request=req.model_dump(exclude_none=True),
        response=response,
        status="degraded",
        duration_ms=int((monotonic() - start) * 1000),
        error=None,
        policy=policy,
    )
    return response


# ── archive_url ──────────────────────────────────────────────────


class ArchiveUrlRequest(BaseModel):
    url: str


@router.post("/archive_url")
async def archive_url(req: ArchiveUrlRequest) -> dict:
    """抓取 URL 内容（受 policy 管控）。"""
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
        _trace(
            tool_name="archive_url",
            request=req.model_dump(exclude_none=True),
            response={"error_code": exc.error_code},
            status="denied",
            duration_ms=int((monotonic() - start) * 1000),
            error=exc.error_code,
            policy={
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
        )
        raise exc

    policy = {
        "allowed": True,
        "reason": decision.reason,
        "domain": decision.domain,
        "robots": decision.robots,
        "cache": {
            "enabled": settings.cache_enabled,
            "ttl_s": settings.cache_ttl_s,
            "hit": False,
        },
    }

    # 真正抓取
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(req.url)
        response = {
            "ok": True,
            "tool": "archive_url",
            "url": req.url,
            "status_code": resp.status_code,
            "content_type": resp.headers.get("content-type", ""),
            "content_length": len(resp.content),
            "text": resp.text[:50_000]
            if resp.headers.get("content-type", "").startswith("text")
            else None,
            "policy": policy,
        }
        status = "ok"
        error = None
    except Exception as exc_fetch:
        response = {
            "ok": False,
            "tool": "archive_url",
            "url": req.url,
            "error": str(exc_fetch),
            "policy": policy,
        }
        status = "error"
        error = str(exc_fetch)

    _trace(
        tool_name="archive_url",
        request=req.model_dump(exclude_none=True),
        response={"ok": response["ok"], "status_code": response.get("status_code")},
        status=status,
        duration_ms=int((monotonic() - start) * 1000),
        error=error,
        policy=policy,
    )
    return response


# ── doc_parse ────────────────────────────────────────────────────


class DocParseRequest(BaseModel):
    artifact_version_uid: str


@router.post("/doc_parse")
async def doc_parse(req: DocParseRequest) -> dict:
    """文档解析：当前无解析后端，返回空结果（降级模式）。"""
    start = monotonic()
    settings = load_settings()
    policy = _policy_block(settings, tool_name="doc_parse")
    response = {
        "ok": True,
        "tool": "doc_parse",
        "artifact_version_uid": req.artifact_version_uid,
        "chunks": [],
    }
    _trace(
        tool_name="doc_parse",
        request=req.model_dump(exclude_none=True),
        response=response,
        status="degraded",
        duration_ms=int((monotonic() - start) * 1000),
        error=None,
        policy=policy,
    )
    return response
