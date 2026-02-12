"""OSINT 采集服务 — 搜索 → 抓取 → 解析 → 去重 → 入库 → 提取声明。

用已有基础设施编排完整 OSINT 流水线：
- SearXNGClient 做网页搜索
- document_parser 做 HTML 解析 + 分块
- ingest_helpers 做 embedding + Qdrant 索引
- source_credibility 做域名评分
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

from aegi_core.infra.searxng_client import SearXNGClient, SearchResult
from aegi_core.services.source_credibility import score_domain

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    urls_found: int = 0
    urls_ingested: int = 0
    urls_deduped: int = 0
    claims_extracted: int = 0
    errors: list[str] = field(default_factory=list)
    artifact_version_uids: list[str] = field(default_factory=list)
    source_claim_uids: list[str] = field(default_factory=list)


class OSINTCollector:
    """OSINT 全流水线采集器：搜索 → 抓取 → 解析 → 去重 → 入库 → 提取声明。"""

    def __init__(
        self,
        searxng: SearXNGClient,
        llm: Any,
        qdrant: Any,
        db_session: Any,
    ) -> None:
        self._searxng = searxng
        self._llm = llm
        self._qdrant = qdrant
        self._db = db_session
        self._http = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "AEGI-OSINT/1.0"},
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def collect(
        self,
        query: str,
        case_uid: str,
        *,
        categories: str = "general",
        language: str = "zh-CN",
        max_results: int = 10,
        extract_claims: bool = True,
    ) -> CollectionResult:
        """执行完整的 OSINT 采集流水线。"""
        result = CollectionResult()

        # 1. 通过 SearXNG 搜索
        search_results = await self._searxng.search(
            query,
            categories=categories,
            language=language,
            limit=max_results,
        )
        result.urls_found = len(search_results)

        if not search_results:
            return result

        # 2. 逐个处理 URL
        for sr in search_results:
            try:
                av_uid = await self._process_url(sr, case_uid, result)
                if av_uid and extract_claims:
                    claim_uids = await self._extract_claims_for_artifact(
                        av_uid, case_uid
                    )
                    result.source_claim_uids.extend(claim_uids)
                    result.claims_extracted += len(claim_uids)
            except Exception as exc:
                msg = f"处理 {sr.url} 出错: {exc}"
                logger.error(msg, exc_info=True)
                result.errors.append(msg)

        return result

    # PLACEHOLDER_PROCESS

    async def _process_url(
        self,
        sr: SearchResult,
        case_uid: str,
        result: CollectionResult,
    ) -> str | None:
        """处理单个 URL：去重 → 抓取 → 解析 → 分块 → 入库。"""
        import sqlalchemy as sa
        from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
        from aegi_core.db.models.chunk import Chunk
        from aegi_core.db.models.evidence import Evidence
        from aegi_core.services.document_parser import parse_html, chunk_text
        from aegi_core.services.ingest_helpers import embed_and_index_chunk

        url = sr.url

        # URL 级去重：检查 ArtifactIdentity.canonical_url
        existing = (
            await self._db.execute(
                sa.select(ArtifactIdentity.uid).where(
                    ArtifactIdentity.canonical_url == url
                )
            )
        ).scalar_one_or_none()
        if existing:
            result.urls_deduped += 1
            return None

        # 抓取内容
        content = await self._fetch_url(url)
        if not content:
            result.errors.append(f"内容为空: {url}")
            return None

        # 内容级去重：检查 ArtifactVersion.content_sha256
        content_sha = hashlib.sha256(content).hexdigest()
        dup = (
            await self._db.execute(
                sa.select(ArtifactVersion.uid).where(
                    ArtifactVersion.case_uid == case_uid,
                    ArtifactVersion.content_sha256 == content_sha,
                )
            )
        ).scalar_one_or_none()
        if dup:
            result.urls_deduped += 1
            return None

        # 解析 HTML → 文本
        text = parse_html(content)
        if len(text.strip()) < 50:
            result.errors.append(f"解析后内容太短: {url}")
            return None

        # 创建 ArtifactIdentity + ArtifactVersion
        ai_uid = f"ai_{uuid4().hex}"
        av_uid = f"av_{uuid4().hex}"
        credibility = score_domain(url)

        self._db.add(ArtifactIdentity(uid=ai_uid, kind="url", canonical_url=url))
        self._db.add(
            ArtifactVersion(
                uid=av_uid,
                artifact_identity_uid=ai_uid,
                case_uid=case_uid,
                content_sha256=content_sha,
                content_type="text/html",
                source_meta={
                    "url": url,
                    "title": sr.title,
                    "snippet": sr.snippet,
                    "engine": sr.engine,
                    "credibility": {
                        "score": credibility.score,
                        "tier": credibility.tier,
                        "reason": credibility.reason,
                    },
                },
            )
        )

        # 分块文本，创建 Chunk + Evidence 记录
        chunks = chunk_text(text)
        for i, chunk_text_str in enumerate(chunks):
            chunk_uid = f"chk_{uuid4().hex}"
            ev_uid = f"ev_{uuid4().hex}"
            self._db.add(
                Chunk(
                    uid=chunk_uid,
                    artifact_version_uid=av_uid,
                    text=chunk_text_str,
                    anchor_set=[],
                    ordinal=i,
                )
            )
            self._db.add(
                Evidence(
                    uid=ev_uid,
                    case_uid=case_uid,
                    artifact_version_uid=av_uid,
                    chunk_uid=chunk_uid,
                    kind="osint_web",
                )
            )
            # 向量化并索引到 Qdrant
            if self._llm and self._qdrant:
                await embed_and_index_chunk(
                    chunk_uid=chunk_uid,
                    text=chunk_text_str,
                    llm=self._llm,
                    qdrant=self._qdrant,
                    metadata={"case_uid": case_uid, "av_uid": av_uid, "url": url},
                )

        await self._db.flush()
        result.urls_ingested += 1
        result.artifact_version_uids.append(av_uid)
        return av_uid

    # PLACEHOLDER_FETCH

    async def _fetch_url(self, url: str) -> bytes:
        """抓取 URL 内容。先用 httpx，JS 渲染页面 fallback 到 Playwright。"""
        try:
            resp = await self._http.get(url)
            resp.raise_for_status()
            content = resp.content
            # 内容太短且包含 <script>，可能是 JS 渲染页面
            text = content.decode("utf-8", errors="ignore")
            if len(text.strip()) < 200 and "<script" in text.lower():
                return await self._fetch_with_playwright(url)
            return content
        except Exception:
            return await self._fetch_with_playwright(url)

    async def _fetch_with_playwright(self, url: str) -> bytes:
        """Playwright fallback，用于 JS 渲染页面。"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                f"playwright not installed, cannot render JS page: {url}"
            )

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            content = await page.content()
            await browser.close()
            return content.encode("utf-8")

    async def _extract_claims_for_artifact(
        self,
        av_uid: str,
        case_uid: str,
    ) -> list[str]:
        """从 artifact version 的所有 chunk 中提取声明。"""
        import sqlalchemy as sa
        from aegi_core.db.models.chunk import Chunk
        from aegi_core.db.models.evidence import Evidence
        from aegi_core.contracts.llm_governance import BudgetContext
        from aegi_core.services.claim_extractor import extract_from_chunk
        from aegi_core.db.models.source_claim import SourceClaim

        if self._llm is None:
            return []

        rows = (
            (
                await self._db.execute(
                    sa.select(Chunk).where(Chunk.artifact_version_uid == av_uid)
                )
            )
            .scalars()
            .all()
        )

        claim_uids: list[str] = []
        budget = BudgetContext(max_tokens=4096, max_cost_usd=1.0)

        for chunk_row in rows:
            ev_row = (
                await self._db.execute(
                    sa.select(Evidence.uid).where(Evidence.chunk_uid == chunk_row.uid)
                )
            ).scalar_one_or_none()

            claims, _, _, _ = await extract_from_chunk(
                chunk_uid=chunk_row.uid,
                chunk_text=chunk_row.text,
                anchor_set=chunk_row.anchor_set,
                artifact_version_uid=av_uid,
                evidence_uid=ev_row or "",
                case_uid=case_uid,
                llm=self._llm,
                budget=budget,
            )
            for c in claims:
                self._db.add(
                    SourceClaim(
                        uid=c.uid,
                        case_uid=c.case_uid,
                        artifact_version_uid=c.artifact_version_uid or av_uid,
                        chunk_uid=c.chunk_uid,
                        evidence_uid=c.evidence_uid or "pending",
                        quote=c.quote,
                        selectors=c.selectors,
                        attributed_to=c.attributed_to,
                        modality=c.modality.value if c.modality else None,
                    )
                )
                claim_uids.append(c.uid)

        if claim_uids:
            await self._db.flush()
        return claim_uids


async def search_preview(
    searxng: SearXNGClient,
    query: str,
    *,
    categories: str = "general",
    language: str = "zh-CN",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """搜索预览 — 返回带可信度评分的结果，不入库。"""
    results = await searxng.search(
        query, categories=categories, language=language, limit=limit
    )
    out = []
    for sr in results:
        cred = score_domain(sr.url)
        out.append(
            {
                "title": sr.title,
                "url": sr.url,
                "snippet": sr.snippet,
                "engine": sr.engine,
                "credibility": {
                    "domain": cred.domain,
                    "score": cred.score,
                    "tier": cred.tier,
                    "reason": cred.reason,
                },
            }
        )
    return out
