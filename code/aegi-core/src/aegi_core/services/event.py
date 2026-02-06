# Author: msq
"""KG event model.

Source: openspec/changes/knowledge-graph-ontology-evolution/design.md
Evidence: 事件类 Assertion 映射为 Event 节点。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EventV1(BaseModel):
    """知识图谱事件节点。"""

    uid: str
    case_uid: str
    label: str
    event_type: str
    timestamp_ref: str | None = None
    properties: dict = Field(default_factory=dict)
    source_assertion_uids: list[str] = Field(default_factory=list)
    ontology_version: str
    created_at: datetime
