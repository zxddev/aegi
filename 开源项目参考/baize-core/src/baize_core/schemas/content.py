"""内容来源标记（用于提示注入隔离与审计）。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ContentSource(str, Enum):
    """内容来源类型。"""

    INTERNAL = "internal"
    EXTERNAL = "external"
    USER = "user"


class TaggedContent(BaseModel):
    """带来源标记的内容片段。"""

    source_type: ContentSource
    content: str = Field(min_length=1)
    source_ref: str | None = None
    content_type: str | None = None
