"""记忆管理器。

实现 episodic（情景）和 semantic（语义）记忆。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """记忆类型。"""

    EPISODIC = "episodic"  # 情景记忆：具体事件、交互历史
    SEMANTIC = "semantic"  # 语义记忆：概念、知识、规则


class MemoryEntry(BaseModel):
    """记忆条目。"""

    memory_id: str = Field(
        default_factory=lambda: f"mem_{uuid4().hex[:12]}",
        description="记忆唯一标识",
    )
    memory_type: MemoryType = Field(description="记忆类型")
    content: str = Field(description="记忆内容")
    context: dict[str, Any] = Field(default_factory=dict, description="上下文信息")
    embedding: list[float] | None = Field(default=None, description="向量嵌入")
    importance: float = Field(default=0.5, ge=0, le=1, description="重要性分数")
    access_count: int = Field(default=0, description="访问次数")
    last_accessed: datetime | None = Field(default=None, description="最后访问时间")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = Field(default=None, description="过期时间")
    tags: list[str] = Field(default_factory=list, description="标签")

    # 情景记忆特有
    episode_id: str | None = Field(default=None, description="情景 ID")
    sequence_index: int | None = Field(default=None, description="序列索引")

    # 语义记忆特有
    concept: str | None = Field(default=None, description="概念名称")
    relations: list[str] = Field(default_factory=list, description="关联的记忆 ID")


class EpisodicMemory(BaseModel):
    """情景记忆：记录具体事件和交互历史。"""

    episode_id: str = Field(
        default_factory=lambda: f"ep_{uuid4().hex[:12]}",
        description="情景唯一标识",
    )
    task_id: str = Field(description="关联任务 ID")
    entries: list[MemoryEntry] = Field(default_factory=list, description="记忆条目")
    summary: str | None = Field(default=None, description="情景摘要")
    outcome: str | None = Field(default=None, description="结果")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def add_entry(
        self,
        content: str,
        context: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> MemoryEntry:
        """添加记忆条目。"""
        entry = MemoryEntry(
            memory_type=MemoryType.EPISODIC,
            content=content,
            context=context or {},
            importance=importance,
            episode_id=self.episode_id,
            sequence_index=len(self.entries),
        )
        self.entries.append(entry)
        return entry

    def get_recent(self, n: int = 10) -> list[MemoryEntry]:
        """获取最近的 n 条记忆。"""
        return self.entries[-n:]

    def get_important(self, threshold: float = 0.7) -> list[MemoryEntry]:
        """获取重要记忆。"""
        return [e for e in self.entries if e.importance >= threshold]


class SemanticMemory(BaseModel):
    """语义记忆：存储概念、知识和规则。"""

    memory_id: str = Field(
        default_factory=lambda: f"sem_{uuid4().hex[:12]}",
        description="语义记忆唯一标识",
    )
    concept: str = Field(description="概念名称")
    definition: str = Field(description="定义")
    examples: list[str] = Field(default_factory=list, description="示例")
    relations: dict[str, list[str]] = Field(
        default_factory=dict, description="关系（关系类型 -> 目标概念列表）"
    )
    properties: dict[str, Any] = Field(default_factory=dict, description="属性")
    confidence: float = Field(default=1.0, ge=0, le=1, description="置信度")
    source: str | None = Field(default=None, description="来源")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def add_relation(self, relation_type: str, target: str) -> None:
        """添加关系。"""
        if relation_type not in self.relations:
            self.relations[relation_type] = []
        if target not in self.relations[relation_type]:
            self.relations[relation_type].append(target)
        self.updated_at = datetime.now(UTC)

    def add_example(self, example: str) -> None:
        """添加示例。"""
        if example not in self.examples:
            self.examples.append(example)
        self.updated_at = datetime.now(UTC)


@runtime_checkable
class MemoryStore(Protocol):
    """记忆存储接口。"""

    async def save_episodic(self, memory: EpisodicMemory) -> None:
        """保存情景记忆。"""
        ...

    async def load_episodic(self, episode_id: str) -> EpisodicMemory | None:
        """加载情景记忆。"""
        ...

    async def save_semantic(self, memory: SemanticMemory) -> None:
        """保存语义记忆。"""
        ...

    async def load_semantic(self, concept: str) -> SemanticMemory | None:
        """加载语义记忆。"""
        ...

    async def search_episodic(
        self, query: str, limit: int = 10
    ) -> list[EpisodicMemory]:
        """搜索情景记忆。"""
        ...

    async def search_semantic(
        self, query: str, limit: int = 10
    ) -> list[SemanticMemory]:
        """搜索语义记忆。"""
        ...


@dataclass
class InMemoryStore:
    """内存记忆存储（用于测试）。"""

    _episodic: dict[str, EpisodicMemory] = field(default_factory=dict)
    _semantic: dict[str, SemanticMemory] = field(default_factory=dict)

    async def save_episodic(self, memory: EpisodicMemory) -> None:
        self._episodic[memory.episode_id] = memory

    async def load_episodic(self, episode_id: str) -> EpisodicMemory | None:
        return self._episodic.get(episode_id)

    async def save_semantic(self, memory: SemanticMemory) -> None:
        self._semantic[memory.concept.lower()] = memory

    async def load_semantic(self, concept: str) -> SemanticMemory | None:
        return self._semantic.get(concept.lower())

    async def search_episodic(
        self, query: str, limit: int = 10
    ) -> list[EpisodicMemory]:
        query_lower = query.lower()
        results = []
        for memory in self._episodic.values():
            if query_lower in (memory.summary or "").lower():
                results.append(memory)
            elif any(query_lower in e.content.lower() for e in memory.entries):
                results.append(memory)
        return results[:limit]

    async def search_semantic(
        self, query: str, limit: int = 10
    ) -> list[SemanticMemory]:
        query_lower = query.lower()
        results = []
        for memory in self._semantic.values():
            if query_lower in memory.concept.lower():
                results.append(memory)
            elif query_lower in memory.definition.lower():
                results.append(memory)
        return results[:limit]


@dataclass
class MemoryManager:
    """记忆管理器。

    统一管理 episodic 和 semantic 记忆。
    """

    store: MemoryStore

    # 当前活跃的情景记忆
    _active_episodes: dict[str, EpisodicMemory] = field(default_factory=dict)

    # 工作记忆（短期）
    _working_memory: list[MemoryEntry] = field(default_factory=list)
    _working_memory_limit: int = 50

    # ==================== 情景记忆 ====================

    def start_episode(self, task_id: str) -> EpisodicMemory:
        """开始新情景。"""
        episode = EpisodicMemory(task_id=task_id)
        self._active_episodes[task_id] = episode
        return episode

    def get_active_episode(self, task_id: str) -> EpisodicMemory | None:
        """获取活跃情景。"""
        return self._active_episodes.get(task_id)

    async def end_episode(
        self,
        task_id: str,
        summary: str | None = None,
        outcome: str | None = None,
    ) -> EpisodicMemory | None:
        """结束情景并保存。"""
        episode = self._active_episodes.pop(task_id, None)
        if episode is None:
            return None

        episode.summary = summary
        episode.outcome = outcome
        await self.store.save_episodic(episode)
        return episode

    def record_event(
        self,
        task_id: str,
        content: str,
        context: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> MemoryEntry | None:
        """记录事件到当前情景。"""
        episode = self._active_episodes.get(task_id)
        if episode is None:
            return None

        entry = episode.add_entry(content, context, importance)
        self._add_to_working_memory(entry)
        return entry

    async def recall_episodes(self, query: str, limit: int = 5) -> list[EpisodicMemory]:
        """回忆相关情景。"""
        return await self.store.search_episodic(query, limit)

    # ==================== 语义记忆 ====================

    async def learn_concept(
        self,
        concept: str,
        definition: str,
        examples: list[str] | None = None,
        relations: dict[str, list[str]] | None = None,
        confidence: float = 1.0,
        source: str | None = None,
    ) -> SemanticMemory:
        """学习新概念。"""
        memory = SemanticMemory(
            concept=concept,
            definition=definition,
            examples=examples or [],
            relations=relations or {},
            confidence=confidence,
            source=source,
        )
        await self.store.save_semantic(memory)
        return memory

    async def recall_concept(self, concept: str) -> SemanticMemory | None:
        """回忆概念。"""
        return await self.store.load_semantic(concept)

    async def search_concepts(self, query: str, limit: int = 5) -> list[SemanticMemory]:
        """搜索概念。"""
        return await self.store.search_semantic(query, limit)

    async def update_concept(
        self,
        concept: str,
        new_examples: list[str] | None = None,
        new_relations: dict[str, list[str]] | None = None,
    ) -> SemanticMemory | None:
        """更新概念。"""
        memory = await self.store.load_semantic(concept)
        if memory is None:
            return None

        if new_examples:
            for ex in new_examples:
                memory.add_example(ex)

        if new_relations:
            for rel_type, targets in new_relations.items():
                for target in targets:
                    memory.add_relation(rel_type, target)

        await self.store.save_semantic(memory)
        return memory

    # ==================== 工作记忆 ====================

    def _add_to_working_memory(self, entry: MemoryEntry) -> None:
        """添加到工作记忆。"""
        self._working_memory.append(entry)
        # 超出限制时移除最旧的
        if len(self._working_memory) > self._working_memory_limit:
            self._working_memory = self._working_memory[-self._working_memory_limit :]

    def get_working_memory(self, n: int | None = None) -> list[MemoryEntry]:
        """获取工作记忆。"""
        if n is None:
            return list(self._working_memory)
        return self._working_memory[-n:]

    def clear_working_memory(self) -> None:
        """清空工作记忆。"""
        self._working_memory.clear()

    def get_context_for_prompt(
        self,
        task_id: str,
        max_entries: int = 10,
    ) -> str:
        """获取上下文用于提示词。"""
        parts = []

        # 当前情景的最近记忆
        episode = self._active_episodes.get(task_id)
        if episode:
            recent = episode.get_recent(max_entries)
            if recent:
                parts.append("## 最近交互")
                for entry in recent:
                    parts.append(f"- {entry.content}")

        # 工作记忆中的重要项
        important = [e for e in self._working_memory if e.importance >= 0.7][
            -max_entries:
        ]
        if important:
            parts.append("## 关键信息")
            for entry in important:
                parts.append(f"- {entry.content}")

        return "\n".join(parts)

    # ==================== 记忆整合 ====================

    async def consolidate_episode(
        self,
        episode: EpisodicMemory,
    ) -> list[SemanticMemory]:
        """整合情景记忆到语义记忆。

        从情景中提取概念和知识。
        """
        # 这里可以使用 LLM 来提取概念
        # 简化实现：从高重要性条目中提取
        concepts = []
        important_entries = episode.get_important(0.8)

        for entry in important_entries:
            # 检查是否有 concept 标签
            for tag in entry.tags:
                if tag.startswith("concept:"):
                    concept_name = tag.split(":", 1)[1]
                    existing = await self.store.load_semantic(concept_name)
                    if existing:
                        existing.add_example(entry.content)
                        await self.store.save_semantic(existing)
                        concepts.append(existing)
                    else:
                        new_concept = await self.learn_concept(
                            concept=concept_name,
                            definition=entry.content,
                            source=f"episode:{episode.episode_id}",
                        )
                        concepts.append(new_concept)

        return concepts
