# Author: msq
"""KG entity model.

Source: openspec/changes/knowledge-graph-ontology-evolution/design.md
Evidence: Assertion 中可识别实体映射为 Entity 节点。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EntityV1(BaseModel):
    """知识图谱实体节点。"""

    uid: str
    case_uid: str
    label: str
    entity_type: str
    properties: dict = Field(default_factory=dict)
    source_assertion_uids: list[str] = Field(default_factory=list)
    ontology_version: str
    created_at: datetime
