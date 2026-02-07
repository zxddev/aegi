# Author: msq
"""KG mapper service — GraphRAG 实体/事件/关系抽取。

Source: openspec/changes/graphrag-entity-extraction/tasks.md
旧规则引擎已删除，现通过 LLM structured output 抽取。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.contracts.errors import ProblemDetail
from aegi_core.services.entity import EntityV1
from aegi_core.services.event import EventV1
from aegi_core.services.relation import RelationV1


@dataclass
class BuildGraphResult:
    """build_graph 的类型安全返回值。"""

    entities: list[EntityV1] = field(default_factory=list)
    events: list[EventV1] = field(default_factory=list)
    relations: list[RelationV1] = field(default_factory=list)
    action: ActionV1 | None = None
    tool_trace: ToolTraceV1 | None = None
    error: ProblemDetail | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
