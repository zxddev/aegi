"""通过 SearXNG 的网页搜索端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from aegi_core.api.deps import get_searxng_client
from aegi_core.infra.searxng_client import SearXNGClient

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def web_search(
    q: str = Query(..., description="搜索关键词"),
    categories: str = Query("general", description="SearXNG 分类"),
    language: str = Query("zh-CN", description="搜索语言"),
    limit: int = Query(10, ge=1, le=50),
    searxng: SearXNGClient = Depends(get_searxng_client),
) -> dict:
    """通过 SearXNG 搜索网页，返回结构化结果。"""
    results = await searxng.search(
        q,
        categories=categories,
        language=language,
        limit=limit,
    )
    return {
        "query": q,
        "count": len(results),
        "results": [
            {"title": r.title, "url": r.url, "snippet": r.snippet, "engine": r.engine}
            for r in results
        ],
    }
