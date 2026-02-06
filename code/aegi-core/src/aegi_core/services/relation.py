# Author: msq
"""KG relation model.

Source: openspec/changes/knowledge-graph-ontology-evolution/design.md
Evidence: 关系由 predicate 规范化映射 Relation 边。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RelationV1(BaseModel):
    """知识图谱关系边。"""

    uid: str
    case_uid: str
    source_entity_uid: str
    target_entity_uid: str
    relation_type: str
    properties: dict = Field(default_factory=dict)
    source_assertion_uids: list[str] = Field(default_factory=list)
    ontology_version: str
    created_at: datetime
