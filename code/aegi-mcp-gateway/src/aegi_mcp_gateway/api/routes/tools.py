# Author: msq

from __future__ import annotations

from time import monotonic

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aegi_mcp_gateway.api.errors import invalid_url, policy_denied, rate_limited
from aegi_mcp_gateway.audit.tool_trace import record_tool_trace
from aegi_mcp_gateway.policy import evaluate_outbound_url
from aegi_mcp_gateway.settings import load_settings


router = APIRouter(prefix="/tools", tags=["tools"])

_HTTP_TIMEOUT = 15.0


# ── 辅助函数 ──────────────────────────────────────────────────────


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


# ── 元搜索 ──────────────────────────────────────────────────────


class MetaSearchRequest(BaseModel):
    q: str
    categories: list[str] | None = None
    language: str | None = None
    safesearch: int | None = None


@router.post("/meta_search")
async def meta_search(req: MetaSearchRequest) -> dict:
    """元搜索：调用 SearxNG。"""
    start = monotonic()
    settings = load_settings()
    policy = _policy_block(settings, tool_name="meta_search")

    params: dict[str, object] = {"q": req.q, "format": "json"}
    if req.categories:
        params["categories"] = ",".join(req.categories)
    if req.language:
        params["language"] = req.language
    if req.safesearch is not None:
        params["safesearch"] = req.safesearch

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(f"{settings.searxng_base_url}/search", params=params)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    response = {"ok": True, "tool": "meta_search", "results": results, "q": req.q}
    _trace(
        tool_name="meta_search",
        request=req.model_dump(exclude_none=True),
        response={"ok": True, "result_count": len(results)},
        status="ok",
        duration_ms=int((monotonic() - start) * 1000),
        error=None,
        policy=policy,
    )
    return response


# ── URL 归档 ──────────────────────────────────────────────────


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

    # 通过 ArchiveBox CLI 归档
    import asyncio
    import json as _json

    container = settings.archivebox_container
    try:
        # 提交归档
        add_proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            "--user=archivebox",
            container,
            "archivebox",
            "add",
            "--index-only",
            req.url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await add_proc.communicate()

        # 查询归档结果
        list_proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            "--user=archivebox",
            container,
            "archivebox",
            "list",
            "--json",
            "--filter-type",
            "exact",
            req.url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await list_proc.communicate()
        snapshots = _json.loads(stdout.decode()) if stdout.strip() else []

        response = {
            "ok": True,
            "tool": "archive_url",
            "url": req.url,
            "archived": len(snapshots) > 0,
            "snapshot": snapshots[0] if snapshots else None,
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


# ── 文档解析 ────────────────────────────────────────────────────


class DocParseRequest(BaseModel):
    artifact_version_uid: str
    file_url: str | None = None


@router.post("/doc_parse")
async def doc_parse(req: DocParseRequest) -> dict:
    """文档解析：调用 Unstructured API。需要 file_url。"""
    start = monotonic()
    settings = load_settings()
    policy = _policy_block(settings, tool_name="doc_parse")

    if not req.file_url:
        raise HTTPException(status_code=422, detail="file_url is required")

    async with httpx.AsyncClient(timeout=60) as client:
        dl = await client.get(req.file_url)
        dl.raise_for_status()
        fname = req.file_url.rsplit("/", 1)[-1] or f"{req.artifact_version_uid}.bin"
        ct = dl.headers.get("content-type", "application/octet-stream")
        resp = await client.post(
            f"{settings.unstructured_base_url}/general/v0/general",
            data={"strategy": "auto"},
            files={"files": (fname, dl.content, ct)},
        )
    resp.raise_for_status()
    elements = resp.json()
    chunks = [
        {"text": el.get("text", ""), "type": el.get("type", ""), "metadata": el.get("metadata", {})}
        for el in elements
        if el.get("text")
    ]
    response = {
        "ok": True,
        "tool": "doc_parse",
        "artifact_version_uid": req.artifact_version_uid,
        "chunks": chunks,
    }
    _trace(
        tool_name="doc_parse",
        request=req.model_dump(exclude_none=True),
        response={"ok": True, "chunk_count": len(chunks)},
        status="ok",
        duration_ms=int((monotonic() - start) * 1000),
        error=None,
        policy=policy,
    )
    return response
