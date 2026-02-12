# Author: msq
"""实体消歧服务测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from aegi_core.services.entity import EntityV1
from aegi_core.services.entity_disambiguator import (
    _alias_canonical,
    _normalize_label,
    disambiguate_entities,
)


def _make_entity(uid: str, label: str, case_uid: str = "case_1") -> EntityV1:
    return EntityV1(
        uid=uid,
        case_uid=case_uid,
        label=label,
        entity_type="actor",
        properties={},
        source_assertion_uids=[],
        ontology_version="v1",
        created_at=datetime.now(timezone.utc),
    )


class TestNormalization:
    """归一化与别名表测试。"""

    def test_normalize_strips_case_and_punctuation(self) -> None:
        assert _normalize_label("  U.S.A.  ") == "usa"

    def test_normalize_unicode(self) -> None:
        # 全角转半角
        assert _normalize_label("Ｃｈｉｎａ") == "china"

    def test_alias_hit(self) -> None:
        assert _alias_canonical("PRC") == "china"
        assert _alias_canonical("中国") == "china"
        assert _alias_canonical("Russian Federation") == "russia"

    def test_alias_miss(self) -> None:
        assert _alias_canonical("Atlantis") is None


class TestRuleDisambiguation:
    """纯规则层消歧（无 LLM）。"""

    async def test_exact_label_merge(self) -> None:
        """相同 label（大小写不同）应合并。"""
        entities = [
            _make_entity("e1", "China"),
            _make_entity("e2", "china"),
        ]
        result = await disambiguate_entities(entities, case_uid="case_1")
        assert len(result.merge_groups) == 1
        g = result.merge_groups[0]
        assert g.canonical_uid == "e1"
        assert g.alias_uids == ["e2"]
        assert g.confidence >= 0.9
        assert not g.uncertain

    async def test_alias_table_merge(self) -> None:
        """已知别名表命中应合并。"""
        entities = [
            _make_entity("e1", "China"),
            _make_entity("e2", "PRC"),
            _make_entity("e3", "中国"),
        ]
        result = await disambiguate_entities(entities, case_uid="case_1")
        assert len(result.merge_groups) == 1
        g = result.merge_groups[0]
        assert len(g.alias_uids) == 2
        assert g.confidence >= 0.9

    async def test_no_merge_for_different_entities(self) -> None:
        """不同实体不应合并。"""
        entities = [
            _make_entity("e1", "China"),
            _make_entity("e2", "Russia"),
        ]
        result = await disambiguate_entities(entities, case_uid="case_1")
        assert len(result.merge_groups) == 0
        assert len(result.unmatched_uids) == 2

    async def test_single_entity_no_merge(self) -> None:
        """单个实体无需消歧。"""
        entities = [_make_entity("e1", "China")]
        result = await disambiguate_entities(entities, case_uid="case_1")
        assert len(result.merge_groups) == 0

    async def test_empty_input(self) -> None:
        result = await disambiguate_entities([], case_uid="case_1")
        assert len(result.merge_groups) == 0
        assert len(result.unmatched_uids) == 0

    async def test_audit_trail(self) -> None:
        """消歧结果包含审计信息。"""
        entities = [
            _make_entity("e1", "USA"),
            _make_entity("e2", "United States"),
        ]
        result = await disambiguate_entities(entities, case_uid="case_1")
        assert result.action.action_type == "kg_disambiguate"
        assert result.tool_trace.tool_name == "entity_disambiguator"
        assert result.tool_trace.status == "ok"

    async def test_mixed_merge_and_unmatched(self) -> None:
        """部分合并、部分未匹配。"""
        entities = [
            _make_entity("e1", "China"),
            _make_entity("e2", "PRC"),
            _make_entity("e3", "Atlantis"),
        ]
        result = await disambiguate_entities(entities, case_uid="case_1")
        assert len(result.merge_groups) == 1
        assert "e3" in result.unmatched_uids


class TestSemanticDisambiguation:
    """语义层消歧（mock embedding）。"""

    @staticmethod
    def _fake_embed_fn() -> dict[str, list[float]]:
        """返回预设 embedding：Beijing/北京 相似，Tokyo 不同。"""
        return {
            "Beijing": [1.0, 0.0, 0.0],
            "北京": [0.98, 0.1, 0.0],  # 与 Beijing 高相似
            "Tokyo": [0.0, 1.0, 0.0],  # 与 Beijing 低相似
        }

    async def test_embedding_merge(self) -> None:
        """embedding 相似度高于阈值应合并。"""
        vecs = self._fake_embed_fn()

        class FakeLLM:
            async def embed(self, text: str, model: str | None = None) -> list[float]:
                return vecs.get(text, [0.0, 0.0, 1.0])

        entities = [
            _make_entity("e1", "Beijing"),
            _make_entity("e2", "北京"),
            _make_entity("e3", "Tokyo"),
        ]
        result = await disambiguate_entities(entities, case_uid="case_1", llm=FakeLLM())
        # Beijing 和 北京 应被语义层合并
        semantic_groups = [
            g for g in result.merge_groups if "embedding" in g.explanation
        ]
        assert len(semantic_groups) == 1
        g = semantic_groups[0]
        assert set([g.canonical_uid] + g.alias_uids) == {"e1", "e2"}
        assert g.confidence > 0.9
        assert not g.uncertain
        # Tokyo 未匹配
        assert "e3" in result.unmatched_uids

    async def test_embedding_low_similarity_no_merge(self) -> None:
        """embedding 相似度低于阈值不应合并。"""

        class FakeLLM:
            async def embed(self, text: str, model: str | None = None) -> list[float]:
                # 所有向量正交
                mapping = {"A": [1, 0, 0], "B": [0, 1, 0], "C": [0, 0, 1]}
                return mapping.get(text, [0, 0, 0])

        entities = [
            _make_entity("e1", "A"),
            _make_entity("e2", "B"),
            _make_entity("e3", "C"),
        ]
        result = await disambiguate_entities(entities, case_uid="case_1", llm=FakeLLM())
        assert len(result.merge_groups) == 0
        assert len(result.unmatched_uids) == 3

    async def test_embedding_failure_graceful(self) -> None:
        """embed 调用失败应跳过该实体，不崩溃。"""

        class FailLLM:
            async def embed(self, text: str, model: str | None = None) -> list[float]:
                raise RuntimeError("embedding service down")

        entities = [
            _make_entity("e1", "Alpha"),
            _make_entity("e2", "Beta"),
        ]
        result = await disambiguate_entities(entities, case_uid="case_1", llm=FailLLM())
        # 不崩溃，全部归入 unmatched
        assert len(result.merge_groups) == 0
        assert len(result.unmatched_uids) == 2
