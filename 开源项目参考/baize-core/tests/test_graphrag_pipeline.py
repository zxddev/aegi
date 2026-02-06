"""GraphRAG 管线测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from baize_core.graph.graphrag_pipeline import (
    GraphRagPipeline,
    _map_entity_type,
    _map_event_type,
)
from baize_core.schemas.entity_event import EntityType, EventType
from baize_core.schemas.evidence import Chunk, ChunkAnchor, Evidence
from baize_core.schemas.extraction import (
    ExtractedEntity,
    ExtractedEntityType,
    ExtractedEvent,
    ExtractedEventParticipant,
    ExtractedEventType,
    ExtractedRelation,
    ExtractedRelationType,
    ExtractionResult,
)


class TestEntityTypeMapping:
    """实体类型映射测试。"""

    def test_映射ACTOR类型(self) -> None:
        """测试 ACTOR 类型映射。"""
        result = _map_entity_type(ExtractedEntityType.ACTOR)
        assert result == EntityType.ACTOR

    def test_映射ORGANIZATION类型(self) -> None:
        """测试 ORGANIZATION 类型映射。"""
        result = _map_entity_type(ExtractedEntityType.ORGANIZATION)
        assert result == EntityType.ORGANIZATION

    def test_映射UNIT类型(self) -> None:
        """测试 UNIT 类型映射。"""
        result = _map_entity_type(ExtractedEntityType.UNIT)
        assert result == EntityType.UNIT


class TestEventTypeMapping:
    """事件类型映射测试。"""

    def test_映射INCIDENT类型(self) -> None:
        """测试 INCIDENT 类型映射。"""
        result = _map_event_type(ExtractedEventType.INCIDENT)
        assert result == EventType.INCIDENT

    def test_映射DEPLOYMENT类型(self) -> None:
        """测试 DEPLOYMENT 类型映射。"""
        result = _map_event_type(ExtractedEventType.DEPLOYMENT)
        assert result == EventType.DEPLOYMENT

    def test_映射EXERCISE类型(self) -> None:
        """测试 EXERCISE 类型映射。"""
        result = _map_event_type(ExtractedEventType.EXERCISE)
        assert result == EventType.EXERCISE


class TestGraphRagPipeline:
    """GraphRagPipeline 集成测试。"""

    @pytest.fixture
    def mock_llm_runner(self) -> MagicMock:
        """创建模拟 LLM 运行器。"""
        runner = MagicMock()
        runner.generate_structured = AsyncMock(
            return_value=MagicMock(
                data=ExtractionResult(
                    entities=[
                        ExtractedEntity(
                            name="美国海军第七舰队",
                            entity_type=ExtractedEntityType.UNIT,
                            description="驻日美军主力舰队",
                        ),
                    ],
                    events=[
                        ExtractedEvent(
                            summary="第七舰队在西太平洋演习",
                            event_type=ExtractedEventType.EXERCISE,
                            confidence=0.8,
                            participants=[
                                ExtractedEventParticipant(
                                    name="美国海军第七舰队",
                                    role="organizer",
                                    entity_type=ExtractedEntityType.UNIT,
                                )
                            ],
                        ),
                        ExtractedEvent(
                            summary="演习结束后舰队返回基地",
                            event_type=ExtractedEventType.MOVEMENT,
                            confidence=0.6,
                        ),
                    ],
                    relations=[
                        ExtractedRelation(
                            source_name="演习结束后舰队返回基地",
                            target_name="第七舰队在西太平洋演习",
                            relation_type=ExtractedRelationType.FOLLOWS,
                            description="演习结束后出现机动/返航活动",
                            confidence=0.7,
                        )
                    ],
                )
            )
        )
        return runner

    @pytest.fixture
    def mock_store(self) -> MagicMock:
        """创建模拟存储。"""
        store = MagicMock()
        store.store_entities = AsyncMock(return_value=["ent_1"])
        store.store_events = AsyncMock(return_value=["evt_1"])
        return store

    @pytest.fixture
    def mock_neo4j_store(self) -> MagicMock:
        """创建模拟 Neo4j 存储。"""
        store = MagicMock()
        store.upsert_entities = AsyncMock()
        store.upsert_events = AsyncMock()
        store.upsert_event_participants = AsyncMock()
        store.upsert_relations = AsyncMock()
        return store

    @pytest.mark.asyncio
    async def test_index_chunks_提取实体和事件(
        self,
        mock_llm_runner: MagicMock,
        mock_store: MagicMock,
        mock_neo4j_store: MagicMock,
    ) -> None:
        """测试 index_chunks 正确提取实体、事件与关系，并解析事件参与方。"""
        pipeline = GraphRagPipeline(
            llm_runner=mock_llm_runner,
            store=mock_store,
            neo4j_store=mock_neo4j_store,
        )

        chunk = Chunk(
            chunk_uid="chk_test",
            artifact_uid="art_test",
            anchor=ChunkAnchor(type="text_offset", ref="0-100"),
            text="美国海军第七舰队在西太平洋进行演习",
            text_sha256="sha256:test",
        )
        evidence = Evidence(
            evidence_uid="evi_test",
            chunk_uid=chunk.chunk_uid,
            source="test_source",
        )

        await pipeline.index_chunks(
            task_id="task_test",
            chunks=[chunk],
            evidence=[evidence],
        )

        # 验证 LLM 被调用
        mock_llm_runner.generate_structured.assert_called_once()

        # 验证存储被调用
        mock_store.store_entities.assert_called_once()
        mock_store.store_events.assert_called_once()

        # 验证 Neo4j 被调用
        mock_neo4j_store.upsert_entities.assert_called_once()
        mock_neo4j_store.upsert_events.assert_called_once()
        mock_neo4j_store.upsert_event_participants.assert_called_once()
        mock_neo4j_store.upsert_relations.assert_called_once()

        # 验证事件参与方被解析为 entity_uid（不会产生悬空外键）
        stored_entities = mock_store.store_entities.call_args[0][0]
        stored_events = mock_store.store_events.call_args[0][0]
        assert stored_entities[0].name == "美国海军第七舰队"
        assert stored_events[0].participants, "事件应包含已解析的参与方"
        assert stored_events[0].participants[0].entity_uid == stored_entities[0].entity_uid

    @pytest.mark.asyncio
    async def test_index_chunks_空chunks不调用存储(
        self,
        mock_llm_runner: MagicMock,
        mock_store: MagicMock,
        mock_neo4j_store: MagicMock,
    ) -> None:
        """测试空 chunks 时不调用存储。"""
        pipeline = GraphRagPipeline(
            llm_runner=mock_llm_runner,
            store=mock_store,
            neo4j_store=mock_neo4j_store,
        )

        await pipeline.index_chunks(
            task_id="task_empty",
            chunks=[],
            evidence=[],
        )

        # 验证 LLM 未被调用
        mock_llm_runner.generate_structured.assert_not_called()

        # 验证存储未被调用
        mock_store.store_entities.assert_not_called()
        mock_store.store_events.assert_not_called()

    @pytest.mark.asyncio
    async def test_index_chunks_无抽取结果不调用存储(
        self,
        mock_store: MagicMock,
        mock_neo4j_store: MagicMock,
    ) -> None:
        """测试无抽取结果时不调用存储。"""
        # 模拟 LLM 返回空结果
        mock_llm = MagicMock()
        mock_llm.generate_structured = AsyncMock(
            return_value=MagicMock(data=ExtractionResult(entities=[], events=[]))
        )

        pipeline = GraphRagPipeline(
            llm_runner=mock_llm,
            store=mock_store,
            neo4j_store=mock_neo4j_store,
        )

        chunk = Chunk(
            chunk_uid="chk_empty",
            artifact_uid="art_empty",
            anchor=ChunkAnchor(type="text_offset", ref="0-50"),
            text="无相关内容的普通文本",
            text_sha256="sha256:empty",
        )

        await pipeline.index_chunks(
            task_id="task_no_result",
            chunks=[chunk],
            evidence=[],
        )

        # 验证 LLM 被调用
        mock_llm.generate_structured.assert_called_once()

        # 验证存储未被调用（因为没有抽取结果）
        mock_store.store_entities.assert_not_called()
        mock_store.store_events.assert_not_called()
