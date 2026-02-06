from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from baize_core.orchestration.ooda_graph import build_ooda_graph
from baize_core.orchestration.review import ReviewAgent
from baize_core.schemas.crew import CrewDecideSummary, CrewOrientSummary
from baize_core.schemas.evidence import Artifact, Chunk, ChunkAnchor, Claim, Evidence
from baize_core.schemas.task import TaskSpec


def test_ooda_graph_reviews_evidence() -> None:
    """测试无 CrewCoordinator 时 OODA 图运行正常。"""
    reviewer = ReviewAgent()
    graph = build_ooda_graph(reviewer)

    artifact = Artifact(
        content_sha256="sha256:1",
        mime_type="text/html",
        storage_ref="minio://bucket/path",
    )
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type="text_offset", ref="0-10"),
        text="测试",
        text_sha256="sha256:chunk",
    )
    evidence = Evidence(chunk_uid=chunk.chunk_uid, source="source", summary="证据")
    claim = Claim(statement="测试结论", evidence_uids=[evidence.evidence_uid])

    state = {
        "task": TaskSpec(task_id="task-1", objective="测试任务"),
        "claims": [claim],
        "evidence": [evidence],
        "chunks": [chunk],
        "artifacts": [artifact],
        "review": None,
    }

    result = asyncio.run(graph.ainvoke(state))
    assert result["review"].ok is True


def test_ooda_graph_with_crew_agent() -> None:
    """测试有 CrewCoordinator 时 OODA 图集成协作输出。"""
    reviewer = ReviewAgent()

    # 模拟 CrewCoordinator
    mock_crew = MagicMock()
    mock_crew.orient = AsyncMock(
        return_value=CrewOrientSummary(
            summary="协作分析摘要：事实较为一致",
            conflicts=["来源可信度差异"],
        )
    )
    mock_crew.decide = AsyncMock(
        return_value=CrewDecideSummary(
            hypotheses=["假设：局势趋于紧张"],
            gaps=["缺少第三方验证"],
        )
    )

    graph = build_ooda_graph(reviewer, crew_agent=mock_crew)

    artifact = Artifact(
        content_sha256="sha256:2",
        mime_type="text/html",
        storage_ref="minio://bucket/path2",
    )
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type="text_offset", ref="0-20"),
        text="协作测试内容",
        text_sha256="sha256:chunk2",
    )
    evidence = Evidence(
        chunk_uid=chunk.chunk_uid,
        source="trusted_source",
        summary="可信证据",
        base_credibility=0.8,
    )
    claim = Claim(statement="协作测试结论", evidence_uids=[evidence.evidence_uid])

    state = {
        "task": TaskSpec(task_id="task-crew", objective="协作测试任务"),
        "claims": [claim],
        "evidence": [evidence],
        "chunks": [chunk],
        "artifacts": [artifact],
        "review": None,
    }

    result = asyncio.run(graph.ainvoke(state))

    # 验证 CrewCoordinator 被调用
    mock_crew.orient.assert_called_once()
    mock_crew.decide.assert_called_once()

    # 验证 orient 输出包含协作摘要
    orient_output = result.get("orient_output")
    assert orient_output is not None
    assert "协作摘要" in orient_output.summary

    # 验证 decide 输出包含协作假设
    decide_output = result.get("decide_output")
    assert decide_output is not None
    assert any("趋于紧张" in h.statement for h in decide_output.hypotheses)

    # 验证审查结果
    assert result["review"].ok is True
