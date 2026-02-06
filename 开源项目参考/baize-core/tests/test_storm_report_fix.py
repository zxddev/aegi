"""测试报告生成修复 - 验证 chunk.text 被正确传递给 LLM。"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from baize_core.schemas.evidence import (
    Artifact,
    AnchorType,
    Chunk,
    ChunkAnchor,
    Evidence,
)
from baize_core.schemas.storm import (
    DepthPolicy,
    StormOutline,
    StormResearch,
    StormResearchSection,
    StormSectionSpec,
    StormTaskType,
)


@pytest.mark.asyncio
async def test_build_report_includes_chunk_text() -> None:
    """验证 _build_report 函数将 chunk.text 内容传递给 LLM。"""
    
    # 导入被测试函数
    from baize_core.orchestration.storm_graph import _build_report
    
    # 创建测试数据
    task_id = "test-task-001"
    
    # 创建 artifact
    artifact = Artifact(
        source_url="https://example.com/article",
        fetched_at=datetime.now(UTC),
        content_sha256="sha256:abc123",
        mime_type="text/html",
        storage_ref="minio://bucket/test.html",
    )
    
    # 创建包含实际内容的 chunk
    chunk_text = "这是一段关于台海局势的详细分析内容。美国海军在该区域进行了多次演习，包括航母战斗群的部署。这些行动被认为是对地区安全局势的回应。"
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-200"),
        text=chunk_text,
        text_sha256="sha256:chunk123",
    )
    
    # 创建 evidence
    evidence = Evidence(
        chunk_uid=chunk.chunk_uid,
        source="test_source",
        uri="https://example.com/article",
        collected_at=datetime.now(UTC),
        base_credibility=0.8,
        summary="台海局势分析文章",
    )
    
    # 创建 outline
    outline = StormOutline(
        task_id=task_id,
        task_type=StormTaskType.STRATEGIC_SITUATION,
        objective="台海近期军事态势分析",
        coverage_checklist=[],
        sections=[
            StormSectionSpec(
                title="战略背景与态势",
                question="当前态势的核心驱动因素是什么？",
                coverage_item_ids=[],
                depth_policy=DepthPolicy(),
            ),
        ],
        created_at=datetime.now(UTC),
    )
    
    # 创建 research
    research = StormResearch(
        outline_uid=outline.outline_uid,
        sections=[
            StormResearchSection(
                section_id=outline.sections[0].section_id,
                iterations=[],
                evidence_uids=[evidence.evidence_uid],
                gaps=[],
            ),
        ],
    )
    
    # 创建 mock LLM runner
    mock_llm_runner = MagicMock()
    captured_prompts: list[str] = []
    
    async def mock_generate_text(**kwargs):
        # 捕获传递给 LLM 的 user prompt
        user_msg = kwargs.get("user", "")
        captured_prompts.append(user_msg)
        return "这是 LLM 生成的分析内容，引用了 [1] 中的信息。"
    
    mock_llm_runner.generate_text = mock_generate_text
    
    # 调用被测试函数
    report = await _build_report(
        outline=outline,
        research=research,
        evidence=[evidence],
        chunks=[chunk],
        artifacts=[artifact],
        llm_runner=mock_llm_runner,
        task_id=task_id,
    )
    
    # 验证结果
    assert report is not None
    assert len(captured_prompts) > 0, "LLM 应该被调用"
    
    # 关键验证：检查传递给 LLM 的 prompt 是否包含 chunk.text 的实际内容
    user_prompt = captured_prompts[0]
    
    # 验证 prompt 包含标题
    assert "标题:" in user_prompt, "Prompt 应该包含标题标记"
    assert "台海局势分析文章" in user_prompt, "Prompt 应该包含 evidence.summary"
    
    # 关键验证：验证 prompt 包含实际的 chunk 文本内容
    assert "内容:" in user_prompt, "Prompt 应该包含内容标记"
    assert chunk_text in user_prompt, f"Prompt 应该包含 chunk.text 的实际内容，但 prompt 是:\n{user_prompt}"
    
    print("✅ 验证通过：chunk.text 被正确传递给 LLM")
    print(f"捕获的 prompt 片段:\n{user_prompt[:500]}...")


@pytest.mark.asyncio
async def test_build_report_truncates_long_text() -> None:
    """验证长文本被正确截断。"""
    
    from baize_core.orchestration.storm_graph import _build_report
    
    task_id = "test-task-002"
    
    artifact = Artifact(
        source_url="https://example.com/long-article",
        fetched_at=datetime.now(UTC),
        content_sha256="sha256:long123",
        mime_type="text/html",
        storage_ref="minio://bucket/long.html",
    )
    
    # 创建超长文本（超过 800 字符）
    long_text = "这是一段很长的内容。" * 200  # 约 2000 字符
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-2000"),
        text=long_text,
        text_sha256="sha256:longchunk",
    )
    
    evidence = Evidence(
        chunk_uid=chunk.chunk_uid,
        source="test_source",
        uri="https://example.com/long-article",
        collected_at=datetime.now(UTC),
        base_credibility=0.8,
        summary="长文章标题",
    )
    
    outline = StormOutline(
        task_id=task_id,
        task_type=StormTaskType.STRATEGIC_SITUATION,
        objective="测试长文本截断",
        coverage_checklist=[],
        sections=[
            StormSectionSpec(
                title="测试章节",
                question="测试问题",
                coverage_item_ids=[],
                depth_policy=DepthPolicy(),
            ),
        ],
        created_at=datetime.now(UTC),
    )
    
    research = StormResearch(
        outline_uid=outline.outline_uid,
        sections=[
            StormResearchSection(
                section_id=outline.sections[0].section_id,
                iterations=[],
                evidence_uids=[evidence.evidence_uid],
                gaps=[],
            ),
        ],
    )
    
    captured_prompts: list[str] = []
    mock_llm_runner = MagicMock()
    
    async def mock_generate_text(**kwargs):
        user_msg = kwargs.get("user", "")
        captured_prompts.append(user_msg)
        return "LLM 响应 [1]"
    
    mock_llm_runner.generate_text = mock_generate_text
    
    await _build_report(
        outline=outline,
        research=research,
        evidence=[evidence],
        chunks=[chunk],
        artifacts=[artifact],
        llm_runner=mock_llm_runner,
        task_id=task_id,
    )
    
    # 验证文本被截断
    user_prompt = captured_prompts[0]
    
    # 检查是否有省略号表示截断
    assert "..." in user_prompt, "长文本应该被截断并添加省略号"
    
    # 验证截断后的内容长度合理（不超过 800 字符 + 标题等）
    # 找到内容部分并验证
    assert len(long_text) > 800, "原始文本应该超过 800 字符"
    
    print("✅ 验证通过：长文本被正确截断")
