"""MCP 工具链契约。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from baize_core.schemas.evidence import Artifact, Chunk


class MetaSearchResult(BaseModel):
    """元搜索结果。"""

    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    snippet: str = Field(min_length=1)
    source: str = Field(min_length=1)
    published_at: datetime | None = None
    score: float = Field(ge=0.0, le=1.0)


class MetaSearchOutput(BaseModel):
    """元搜索输出。"""

    results: list[MetaSearchResult]


class WebCrawlOutput(BaseModel):
    """抓取输出。"""

    artifact: Artifact


class ArchiveUrlOutput(BaseModel):
    """归档输出。"""

    artifact: Artifact


class DocParseOutput(BaseModel):
    """解析输出。"""

    chunks: list[Chunk]
