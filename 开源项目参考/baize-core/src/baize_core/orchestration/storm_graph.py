"""STORM 编排图。

支持检查点机制，实现状态持久化与恢复。
集成 DeepResearchLoop 和 DepthController 实现动态深度控制。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

from baize_core.agents.watchlist import WatchlistExtractor, format_watchlist_markdown
from baize_core.evidence.validator import ConflictEntry, ConflictTable
from baize_core.graph.graphrag_pipeline import GraphRagPipeline
from baize_core.llm.context_engine import (
    EvidenceCandidate,
    PromptBudget,
    SectionWriteConfig,
    SectionWriter,
    WriterStrategy,
    create_candidates_from_evidence_chain,
)
from baize_core.llm.prompt_builder import PromptBuilder
from baize_core.llm.runner import LlmRunner
from baize_core.orchestration.deep_research import (
    DeepResearchConfig,
    DeepResearchLoop,
    ResearchContext,
    SectionSpec,
    SimpleCritic,
)
from baize_core.orchestration.review import ReviewAgent
from baize_core.orchestration.storm_templates import build_outline_sections_from_config
from baize_core.policy.depth import DepthConfig, DepthController
from baize_core.schemas.content import ContentSource
from baize_core.schemas.evidence import (
    Artifact,
    Chunk,
    Evidence,
    Report,
    ReportReference,
)
from baize_core.schemas.mcp_toolchain import (
    ArchiveUrlOutput,
    DocParseOutput,
    MetaSearchOutput,
    WebCrawlOutput,
)
from baize_core.schemas.policy import StageType
from baize_core.schemas.review import ReviewResult
from baize_core.schemas.storm import (
    DepthPolicy,
    ReportConfig,
    SectionType,
    StormIteration,
    StormOutline,
    StormReport,
    StormReportSection,
    StormResearch,
    StormResearchSection,
    StormSectionSpec,
    StormTaskType,
)
from baize_core.schemas.task import TaskSpec
from baize_core.storage.minio_store import MinioArtifactStore
from baize_core.storage.postgres import PostgresStore
from baize_core.tools.runner import ToolRunner
from baize_core.modules.registry import ModuleRegistry
from baize_core.modules.parser import UserInputParser


class StormState(TypedDict):
    """STORM 状态。"""

    task: TaskSpec
    report_config: ReportConfig
    outline: StormOutline | None
    research: StormResearch | None
    report: StormReport | None
    report_record: Report | None
    evidence: list[Evidence]
    chunks: list[Chunk]
    artifacts: list[Artifact]
    review: ReviewResult | None


@dataclass(frozen=True)
class StormContext:
    """STORM 运行上下文。"""

    store: PostgresStore
    artifact_store: MinioArtifactStore
    tool_runner: ToolRunner
    reviewer: ReviewAgent
    llm_runner: LlmRunner
    module_registry: ModuleRegistry
    input_parser: UserInputParser
    graph_pipeline: GraphRagPipeline | None = None
    checkpointer: Any | None = None
    depth_controller: DepthController | None = None
    enable_dynamic_depth: bool = True
    enable_critic_review: bool = True
    skip_review_validation: bool = False  # 跳过 review 严格校验


def build_storm_graph(context: StormContext) -> object:
    """构建 STORM 编排图。"""

    try:
        from langgraph.graph import END, START, StateGraph
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 langgraph") from exc

    async def outline_node(state: StormState) -> StormState:
        task = state["task"]
        report_config = state["report_config"]
        sections, coverage = await build_outline_sections_from_config(
            task_id=task.task_id,
            report_config=report_config,
            module_registry=context.module_registry,
            input_parser=context.input_parser,
            llm_runner=context.llm_runner,
        )
        outline = StormOutline(
            task_id=task.task_id,
            # 旧模板已废弃：此字段仅用于持久化占位
            task_type=StormTaskType.STRATEGIC_SITUATION,
            objective=task.objective,
            report_config=report_config,
            coverage_checklist=coverage,
            sections=sections,
            created_at=datetime.now(UTC),
        )
        await context.store.store_storm_outline(outline)
        return {**state, "outline": outline}

    async def research_node(state: StormState) -> StormState:
        outline = state.get("outline")
        if outline is None:
            raise ValueError("缺少大纲")

        # 创建 DeepResearchLoop 实例
        depth_controller = context.depth_controller
        if depth_controller is None and context.enable_dynamic_depth:
            # 使用默认配置创建 DepthController
            depth_controller = DepthController(config=DepthConfig())

        research_context = ResearchContext(
            store=context.store,
            tool_runner=context.tool_runner,
            llm_runner=context.llm_runner,
            depth_controller=depth_controller,
            critic=SimpleCritic() if context.enable_critic_review else None,
        )
        research_config = DeepResearchConfig(
            enable_dynamic_depth=context.enable_dynamic_depth,
            enable_critic_review=context.enable_critic_review,
        )
        deep_research = DeepResearchLoop(
            context=research_context,
            config=research_config,
        )

        evidence_map: dict[str, Evidence] = {}
        chunk_map: dict[str, Chunk] = {}
        artifact_map: dict[str, Artifact] = {}
        research_sections: list[StormResearchSection] = []

        for section in outline.sections:
            # 使用 DeepResearchLoop 执行章节研究
            section_spec = SectionSpec(
                section_id=section.section_id,
                title=section.title,
                question=section.question,
                depth_policy=section.get_effective_depth_policy(),
            )
            result = await deep_research.run_section_research(
                task_id=state["task"].task_id,
                objective=outline.objective,
                section=section_spec,
            )

            # 转换为 StormResearchSection
            storm_iterations = [
                StormIteration(
                    section_id=section.section_id,
                    iteration_index=it.iteration_index,
                    query=it.query,
                    evidence_uids=it.evidence_uids,
                )
                for it in result.iterations
            ]
            research_section = StormResearchSection(
                section_id=section.section_id,
                iterations=storm_iterations,
                evidence_uids=[e.evidence_uid for e in result.evidence],
                gaps=result.gaps,
            )
            research_sections.append(research_section)

            # 收集证据链
            for evidence in result.evidence:
                evidence_map[evidence.evidence_uid] = evidence
            for chunk in result.chunks:
                chunk_map[chunk.chunk_uid] = chunk
            for artifact in result.artifacts:
                artifact_map[artifact.artifact_uid] = artifact

        research = StormResearch(
            outline_uid=outline.outline_uid, sections=research_sections
        )
        return {
            **state,
            "research": research,
            "evidence": list(evidence_map.values()),
            "chunks": list(chunk_map.values()),
            "artifacts": list(artifact_map.values()),
        }

    async def report_node(state: StormState) -> StormState:
        outline = state.get("outline")
        research = state.get("research")
        if outline is None or research is None:
            raise ValueError("缺少研究数据")
        if context.graph_pipeline is not None and state["chunks"]:
            await context.graph_pipeline.index_chunks(
                task_id=state["task"].task_id,
                chunks=state["chunks"],
                evidence=state["evidence"],
            )
        report = await _build_report(
            outline=outline,
            research=research,
            evidence=state["evidence"],
            chunks=state["chunks"],
            artifacts=state["artifacts"],
            llm_runner=context.llm_runner,
            task_id=state["task"].task_id,
        )
        return {**state, "report": report}

    async def review_node(state: StormState) -> StormState:
        report = state.get("report")
        if report is None:
            raise ValueError("缺少报告")
        result = context.reviewer.review(
            claims=[],
            evidence=state["evidence"],
            chunks=state["chunks"],
            artifacts=state["artifacts"],
            report=Report(
                report_uid=report.report_uid,
                task_id=report.task_id,
                outline_uid=report.outline_uid,
                report_type=report.report_type.value,
                content_ref="pending",
                references=report.references,
                conflict_notes=report.conflict_notes,
                markdown=report.markdown,
            ),
        )
        # 检查是否跳过严格校验
        if not result.ok and not context.skip_review_validation:
            error_details = ", ".join(result.missing_evidence[:5]) if result.missing_evidence else "未知错误"
            raise ValueError(f"报告引用校验失败: {error_details}")
        object_name = f"reports/{report.report_uid}.md"
        await context.artifact_store.ensure_bucket()
        await context.artifact_store.put_text(
            object_name=object_name,
            text=report.markdown,
            content_type="text/markdown",
        )
        report_record = Report(
            report_uid=report.report_uid,
            task_id=report.task_id,
            outline_uid=report.outline_uid,
            report_type=report.report_type.value,
            content_ref=f"minio://{context.artifact_store.bucket}/{object_name}",
            references=report.references,
            conflict_notes=report.conflict_notes,
        )
        await context.store.store_report(report_record)
        return {**state, "review": result, "report_record": report_record}

    research_builder = StateGraph(StormState)
    research_builder.add_node("research_inner", research_node)
    research_builder.add_edge(START, "research_inner")
    research_builder.add_edge("research_inner", END)
    research_graph = research_builder.compile()

    builder = StateGraph(StormState)
    builder.add_node("outline", outline_node)
    builder.add_node("research", research_graph)
    builder.add_node("report", report_node)
    builder.add_node("review", review_node)
    builder.add_edge(START, "outline")
    builder.add_edge("outline", "research")
    builder.add_edge("research", "report")
    builder.add_edge("report", "review")
    builder.add_edge("review", END)

    # 如果提供了检查点存储，启用状态持久化
    if context.checkpointer is not None:
        return builder.compile(checkpointer=context.checkpointer)
    return builder.compile()


@dataclass(frozen=True)
class _SectionResearchBundle:
    """章节研究扩展结果。"""

    section: StormResearchSection
    evidence_lookup: dict[str, Evidence]
    chunk_lookup: dict[str, Chunk]
    artifact_lookup: dict[str, Artifact]


async def _run_section_research(
    *,
    context: StormContext,
    task: TaskSpec,
    outline: StormOutline,
    section: StormSectionSpec,
) -> _SectionResearchBundle:
    depth_policy = section.depth_policy
    min_sources = depth_policy.min_sources
    max_iterations = depth_policy.max_iterations
    seen_urls: set[str] = set()
    seen_domains: set[str] = set()
    seen_hashes: set[str] = set()
    evidence_map: dict[str, Evidence] = {}
    chunk_map: dict[str, Chunk] = {}
    artifact_map: dict[str, Artifact] = {}
    iterations: list[StormIteration] = []
    for iteration in range(1, max_iterations + 1):
        query = _build_query(
            task=task, outline=outline, section=section, iteration=iteration
        )
        artifacts, chunks, evidence_items, prestored_artifacts = await _run_toolchain(
            context=context,
            task_id=task.task_id,
            query=query,
            depth_policy=depth_policy,
        )
        filtered_artifacts, filtered_chunks, filtered_evidence = _dedupe_results(
            artifacts=artifacts,
            chunks=chunks,
            evidence_items=evidence_items,
            seen_urls=seen_urls,
            seen_domains=seen_domains,
            seen_hashes=seen_hashes,
            dedupe_by_domain=depth_policy.dedupe_by_domain,
        )
        artifacts_to_store = [
            artifact
            for artifact in filtered_artifacts
            if artifact.artifact_uid not in prestored_artifacts
        ]
        if artifacts_to_store or filtered_chunks or filtered_evidence:
            await context.store.store_evidence_chain(
                artifacts=artifacts_to_store,
                chunks=filtered_chunks,
                evidence_items=filtered_evidence,
                claims=[],
            )
        for artifact in filtered_artifacts:
            artifact_map[artifact.artifact_uid] = artifact
            seen_hashes.add(artifact.content_sha256)
        for chunk in filtered_chunks:
            chunk_map[chunk.chunk_uid] = chunk
        for evidence in filtered_evidence:
            evidence_map[evidence.evidence_uid] = evidence
            if evidence.uri:
                seen_urls.add(evidence.uri)
                if depth_policy.dedupe_by_domain:
                    domain = urlparse(evidence.uri).netloc
                    if domain:
                        seen_domains.add(domain)
        iteration_record = StormIteration(
            section_id=section.section_id,
            iteration_index=iteration,
            query=query,
            evidence_uids=[item.evidence_uid for item in filtered_evidence],
        )
        iterations.append(iteration_record)
        await context.store.store_storm_iterations([iteration_record])
        await context.store.store_storm_section_evidence(
            section_uid=section.section_id,
            evidence_uids=[item.evidence_uid for item in filtered_evidence],
        )
        if len(evidence_map) >= min_sources:
            break
    gaps: list[str] = []
    if len(evidence_map) < min_sources:
        gaps.append("来源数量不足")
    return _SectionResearchBundle(
        section=StormResearchSection(
            section_id=section.section_id,
            iterations=iterations,
            evidence_uids=list(evidence_map.keys()),
            gaps=gaps,
        ),
        evidence_lookup=evidence_map,
        chunk_lookup=chunk_map,
        artifact_lookup=artifact_map,
    )


def _build_query(
    *,
    task: TaskSpec,
    outline: StormOutline,
    section: StormSectionSpec,
    iteration: int,
) -> str:
    """构建搜索查询。
    
    使用 section.question 替代 title，因为 question 更具体、更适合搜索。
    例如：
    - title: "关键参与方与能力"
    - question: "关键参与方与权力结构如何？"
    question 能获得更好的搜索结果。
    """
    suffix = "补充来源" if iteration > 1 else ""
    # 优先使用 question，因为它更具体
    search_term = section.question if section.question else section.title
    return f"{task.objective} {search_term} {suffix}".strip()


async def _run_toolchain(
    *,
    context: StormContext,
    task_id: str,
    query: str,
    depth_policy: DepthPolicy,
) -> tuple[list[Artifact], list[Chunk], list[Evidence], set[str]]:
    search_payload: dict[str, object] = {
        "query": query,
        "max_results": depth_policy.max_results,
        "language": depth_policy.language,
        "time_range": depth_policy.time_range,
    }
    search_response = await context.tool_runner.run_mcp(
        tool_name="meta_search",
        tool_input=search_payload,
        stage=StageType.OBSERVE,
        task_id=task_id,
    )
    search_output = MetaSearchOutput.model_validate(search_response)
    if len(search_output.results) > depth_policy.max_results:
        raise ValueError("meta_search 返回结果数量超过限制")
    artifacts: list[Artifact] = []
    chunks: list[Chunk] = []
    evidence_items: list[Evidence] = []
    prestored_artifacts: set[str] = set()
    for result in search_output.results:
        crawl_payload: dict[str, object] = {
            "url": result.url,
            "max_depth": depth_policy.max_depth,
            "max_pages": depth_policy.max_pages,
            "obey_robots_txt": depth_policy.obey_robots_txt,
            "timeout_ms": depth_policy.timeout_ms,
        }
        crawl_response = await context.tool_runner.run_mcp(
            tool_name="web_crawl",
            tool_input=crawl_payload,
            stage=StageType.OBSERVE,
            task_id=task_id,
        )
        crawl_output = WebCrawlOutput.model_validate(crawl_response)
        crawl_output.artifact.origin_tool = "web_crawl"
        artifacts.append(crawl_output.artifact)
        await context.store.store_artifacts([crawl_output.artifact])

        archive_payload: dict[str, object] = {"url": result.url}
        archive_response = await context.tool_runner.run_mcp(
            tool_name="archive_url",
            tool_input=archive_payload,
            stage=StageType.OBSERVE,
            task_id=task_id,
        )
        archive_output = ArchiveUrlOutput.model_validate(archive_response)
        archive_output.artifact.origin_tool = "archive_url"
        artifacts.append(archive_output.artifact)
        await context.store.store_artifacts([archive_output.artifact])
        prestored_artifacts.add(archive_output.artifact.artifact_uid)

        parse_payload: dict[str, object] = {
            "artifact_uid": archive_output.artifact.artifact_uid,
            "chunk_size": depth_policy.chunk_size,
            "chunk_overlap": depth_policy.chunk_overlap,
        }
        parse_response = await context.tool_runner.run_mcp(
            tool_name="doc_parse",
            tool_input=parse_payload,
            stage=StageType.OBSERVE,
            task_id=task_id,
        )
        parse_output = DocParseOutput.model_validate(parse_response)
        for chunk in parse_output.chunks:
            if chunk.artifact_uid != archive_output.artifact.artifact_uid:
                raise ValueError("解析结果 Artifact 不一致")
        chunks.extend(parse_output.chunks)
        for chunk in parse_output.chunks:
            evidence_items.append(
                Evidence(
                    chunk_uid=chunk.chunk_uid,
                    source=result.source,
                    uri=result.url,
                    collected_at=archive_output.artifact.fetched_at,
                    base_credibility=result.score,
                    tags=[f"source:{result.source}"],
                    summary=result.title,
                )
            )
    return artifacts, chunks, evidence_items, prestored_artifacts


def _dedupe_results(
    *,
    artifacts: list[Artifact],
    chunks: list[Chunk],
    evidence_items: list[Evidence],
    seen_urls: set[str],
    seen_domains: set[str],
    seen_hashes: set[str],
    dedupe_by_domain: bool,
) -> tuple[list[Artifact], list[Chunk], list[Evidence]]:
    artifact_map = {artifact.artifact_uid: artifact for artifact in artifacts}
    chunk_map = {chunk.chunk_uid: chunk for chunk in chunks}
    filtered_evidence: list[Evidence] = []
    allowed_artifacts: dict[str, Artifact] = {}
    allowed_chunks: dict[str, Chunk] = {}
    for evidence in evidence_items:
        if evidence.uri and evidence.uri in seen_urls:
            continue
        domain = urlparse(evidence.uri or "").netloc
        if dedupe_by_domain and domain and domain in seen_domains:
            continue
        chunk = chunk_map.get(evidence.chunk_uid)
        if chunk is None:
            continue
        artifact = artifact_map.get(chunk.artifact_uid)
        if artifact is None:
            continue
        normalized_hash = artifact.content_sha256.removeprefix("sha256:")
        if normalized_hash in seen_hashes:
            continue
        allowed_artifacts[artifact.artifact_uid] = artifact
        allowed_chunks[chunk.chunk_uid] = chunk
        filtered_evidence.append(evidence)
        seen_hashes.add(normalized_hash)
    return (
        list(allowed_artifacts.values()),
        list(allowed_chunks.values()),
        filtered_evidence,
    )


async def _build_report(
    *,
    outline: StormOutline,
    research: StormResearch,
    evidence: list[Evidence],
    chunks: list[Chunk],
    artifacts: list[Artifact],
    llm_runner: LlmRunner,
    task_id: str,
) -> StormReport:
    evidence_map = {item.evidence_uid: item for item in evidence}
    chunk_map = {item.chunk_uid: item for item in chunks}
    artifact_map = {item.artifact_uid: item for item in artifacts}
    references: list[ReportReference] = []
    sections: list[StormReportSection] = []
    
    # 配置：使用新的上下文工程层或旧的实现
    use_context_engine = os.environ.get("BAIZE_USE_CONTEXT_ENGINE", "true").lower() == "true"
    writer_strategy_str = os.environ.get("BAIZE_WRITER_STRATEGY", "single_pass")
    writer_strategy = WriterStrategy(writer_strategy_str) if writer_strategy_str in [s.value for s in WriterStrategy] else WriterStrategy.SINGLE_PASS
    
    # 创建 SectionWriter 的 LLM 调用适配器
    async def llm_call_adapter(system: str, user: str) -> str:
        return await llm_runner.generate_text(
            system=system,
            user=user,
            stage=StageType.SYNTHESIS,
            task_id=task_id,
        )
    
    # 创建 SectionWriter
    section_writer = SectionWriter(
        llm_call=llm_call_adapter,
        config=SectionWriteConfig(
            strategy=writer_strategy,
            budget=PromptBudget(
                max_tokens=8000,
                max_chars=32000,
                max_evidence_count=15,
                max_chars_per_evidence=800,
            ),
            batch_size=8,
        ),
    )
    
    citation_counter = 1
    
    for section in research.sections:
        outline_section = _find_section(outline.sections, section.section_id)
        if outline_section is None:
            continue
        
        # 收集该章节的证据
        section_evidence = [
            evidence_map[uid] for uid in section.evidence_uids
            if uid in evidence_map
        ]
        
        if not section_evidence:
            sections.append(
                StormReportSection(
                    section_id=section.section_id,
                    title=outline_section.title,
                    markdown=f"### {outline_section.title}\n\n证据不足，无法生成分析。",
                    evidence_uids=[],
                )
            )
            continue
        
        if use_context_engine:
            # ========== 使用新的上下文工程层 ==========
            # 1. 创建候选列表
            candidates = create_candidates_from_evidence_chain(
                evidence_items=section_evidence,
                chunk_map=chunk_map,
                artifact_map=artifact_map,
            )
            
            logger.info(
                "章节 %s: 使用上下文工程层, %d 条证据, 策略 %s",
                outline_section.title, len(candidates), writer_strategy.value
            )
            
            # 2. 调用 SectionWriter
            write_result = await section_writer.write_section(
                section_id=section.section_id,
                title=outline_section.title,
                question=outline_section.question,
                objective=outline.objective,
                candidates=candidates,
                prompt_profile=outline_section.prompt_profile,
                user_context=outline.report_config.user_context
                if outline.report_config
                else None,
            )
            
            # 3. 将“章节内局部引用编号”重写为“全局唯一引用编号”
            import re

            local_map_raw = (write_result.metadata or {}).get("citation_evidence_uid_map", {})
            local_map: dict[int, str] = (
                {int(k): str(v) for k, v in local_map_raw.items()}
                if isinstance(local_map_raw, dict)
                else {}
            )
            local_citations = sorted(
                {
                    int(item)
                    for item in write_result.citations_used
                    if int(item) in local_map
                }
            )
            citation_map: dict[int, int] = {}
            for local in local_citations:
                citation_map[local] = citation_counter
                citation_counter += 1

            def _rewrite_citation(match: re.Match[str]) -> str:
                local = int(match.group(1))
                global_id = citation_map.get(local)
                # 未映射的编号（多为编造/越界引用）直接移除，避免引用校验失败
                return f"[{global_id}]" if global_id is not None else ""

            rewritten_markdown = re.sub(r"\[(\d+)\]", _rewrite_citation, write_result.markdown)

            # 4. 构建 ReportReference（仅包含正文出现的引用）
            for local in local_citations:
                evidence_uid = local_map.get(local)
                if not evidence_uid:
                    continue
                ev = evidence_map.get(evidence_uid)
                if ev is None:
                    continue
                chunk = chunk_map.get(ev.chunk_uid)
                if chunk is None:
                    continue
                references.append(
                    ReportReference(
                        citation=citation_map[local],
                        evidence_uid=ev.evidence_uid,
                        chunk_uid=chunk.chunk_uid,
                        artifact_uid=chunk.artifact_uid,
                        source_url=ev.uri,
                        anchor=chunk.anchor,
                    )
                )

            # 5. 构建章节 markdown
            section_markdown = f"### {outline_section.title}\n\n{rewritten_markdown.strip()}"
            
            if write_result.degraded:
                logger.warning(
                    "章节 %s 降级: %s",
                    outline_section.title, write_result.degradation_reason
                )
        else:
            # ========== 旧实现（向后兼容）==========
            lines = [f"### {outline_section.title}"]
            section_sources: list[str] = []
            
            for evidence_item in section_evidence:
                chunk = chunk_map.get(evidence_item.chunk_uid)
                if chunk is None:
                    continue
                artifact = artifact_map.get(chunk.artifact_uid)
                if artifact is None:
                    continue
                
                citation = citation_counter
                citation_counter += 1
                
                title = evidence_item.summary or evidence_item.uri or "证据"
                if evidence_item.conflict_types:
                    title = f"{title}（冲突证据）"
                content_preview = chunk.text[:500] if chunk.text else ""
                if len(chunk.text) > 500:
                    content_preview += "..."
                evidence_entry = f"[{citation}] 标题: {title}\n内容: {content_preview}"
                section_sources.append(evidence_entry)
                
                if sum(len(s) for s in section_sources) > 30000:
                    break
                
                references.append(
                    ReportReference(
                        citation=citation,
                        evidence_uid=evidence_item.evidence_uid,
                        chunk_uid=chunk.chunk_uid,
                        artifact_uid=artifact.artifact_uid,
                        source_url=evidence_item.uri,
                        anchor=chunk.anchor,
                    )
                )
            
            if section_sources:
                sources_block = "\n\n".join(section_sources)
                user_query = (
                    f"任务目标：{outline.objective}\n"
                    f"章节标题：{outline_section.title}\n"
                    f"章节问题：{outline_section.question}\n\n"
                    "写作要求：\n"
                    "1. 输出 4-8 段深度分析\n"
                    "2. 每段必须包含引用标记\n"
                    "3. 引用标记使用证据编号\n\n"
                    "证据清单：\n" + sources_block
                )
                section_body = await llm_runner.generate_text(
                    system=_section_system_prompt(),
                    user=user_query,
                    stage=StageType.SYNTHESIS,
                    task_id=task_id,
                    section_id=section.section_id,
                )
                lines.append(section_body.strip())
            else:
                lines.append("证据不足，无法生成分析。")
            
            section_markdown = "\n\n".join(lines).strip()
        
        sections.append(
            StormReportSection(
                section_id=section.section_id,
                title=outline_section.title,
                markdown=section_markdown,
                evidence_uids=section.evidence_uids,
            )
        )
    title = "研究报告"
    if outline.report_config and outline.report_config.title:
        candidate = outline.report_config.title.strip()
        if candidate:
            title = candidate

    header = [f"# {title}", f"任务：{outline.objective}"]
    if outline.report_config and outline.report_config.selected_modules:
        module_titles = "、".join(
            m.title for m in outline.report_config.selected_modules if m.title
        ).strip()
        if module_titles:
            header.append(f"模块：{module_titles}")
    header.append("")
    body = [section.markdown for section in sections]
    markdown = "\n\n".join(header + body).strip()

    # Watchlist 抽取（仅当大纲包含 Watchlist 章节时启用）
    watchlist_markdown = await _extract_watchlist(
        outline=outline,
        sections=sections,
        evidence=evidence,
        llm_runner=llm_runner,
        task_id=task_id,
    )
    if watchlist_markdown:
        markdown = "\n\n".join([markdown, watchlist_markdown]).strip()

    # 冲突表嵌入（如存在冲突）
    conflict_entries: list[ConflictEntry] = []
    total_conflicts = 0
    for ev in evidence:
        if ev.conflict_types:
            total_conflicts += len(ev.conflict_types)
            conflict_entries.append(
                ConflictEntry(
                    evidence_uid=ev.evidence_uid,
                    conflict_types=list(ev.conflict_types),
                    conflict_with=list(ev.conflict_with) if ev.conflict_with else [],
                    summary=ev.summary or "",
                )
            )
    conflict_notes = None
    if conflict_entries:
        conflict_table = ConflictTable(
            entries=conflict_entries,
            total_conflicts=total_conflicts,
        )
        conflict_notes = conflict_table.to_markdown()
        if conflict_notes:
            markdown = "\n\n".join([markdown, conflict_notes]).strip()

    report = StormReport(
        outline_uid=outline.outline_uid,
        task_id=outline.task_id,
        report_type=outline.task_type,
        title=title,
        markdown=markdown,
        sections=sections,
        references=references,
        conflict_notes=conflict_notes,
    )
    return report


def _find_section(
    sections: list[StormSectionSpec], section_id: str
) -> StormSectionSpec | None:
    for section in sections:
        if section.section_id == section_id:
            return section
    return None


def _section_system_prompt() -> str:
    """章节写作系统提示。"""

    return (
        "你是资深军事情报分析员，负责撰写深度研究报告章节。\n\n"
        "核心要求：\n"
        "1. 必须使用证据清单中提供的引用编号（如 [1], [2], [3]），不得编造编号\n"
        "2. 每个事实性陈述都要标注引用，格式为 [编号]\n"
        "3. 输出 4-8 段深度分析，每段 100-200 字\n"
        "4. 分析要有层次：背景→现状→趋势→影响\n"
        "5. 不允许超出证据材料范围进行推测\n"
        "6. 如有矛盾证据，需指出分歧并分析可能原因"
    )


def _build_section_prompt(
    *,
    objective: str,
    section_title: str,
    section_question: str,
    sources: list[str],
) -> str:
    """构建章节提示。"""

    sources_block = "\n".join(sources) if sources else "(无可用证据)"
    return (
        f"任务目标：{objective}\n"
        f"章节标题：{section_title}\n"
        f"章节问题：{section_question}\n"
        "证据清单：\n"
        f"{sources_block}\n\n"
        "要求：\n"
        "1. 用 2-4 段输出分析。\n"
        "2. 每段至少包含一个引用编号。\n"
        "3. 引用编号必须来自证据清单。\n"
    )


async def _extract_watchlist(
    *,
    outline: StormOutline,
    sections: list[StormReportSection],
    evidence: list[Evidence],
    llm_runner: LlmRunner,
    task_id: str,
) -> str:
    """抽取观察指标（Watchlist）并生成 Markdown。

    仅当大纲包含 Watchlist 章节时启用抽取。

    Args:
        outline: 报告大纲
        sections: 已生成的章节列表
        evidence: 证据列表
        llm_runner: LLM 运行器
        task_id: 任务 ID

    Returns:
        Watchlist Markdown 文本（如无则返回空字符串）
    """
    # 检查大纲中是否有 Watchlist 章节
    watchlist_section = None
    for section in outline.sections:
        if section.section_type == SectionType.WATCHLIST:
            watchlist_section = section
            break

    if watchlist_section is None:
        return ""

    # 收集所有章节内容作为抽取输入
    all_content = "\n\n".join(
        section.markdown for section in sections if section.markdown
    )
    if not all_content.strip():
        return ""

    # 收集已知实体名称（用于关联）
    entity_names: list[str] = []
    for ev in evidence:
        if ev.summary:
            entity_names.append(ev.summary[:50])

    # 使用 WatchlistExtractor 抽取
    extractor = WatchlistExtractor(max_items=10)

    # 优先使用 LLM 抽取，若无 LLM 则使用规则抽取
    try:
        result = await extractor.extract_with_llm(
            text=all_content,
            llm_runner=llm_runner,
            stage=StageType.SYNTHESIS,
            task_id=task_id,
            section_id=watchlist_section.section_id,
        )
    except Exception:
        # 降级到规则抽取
        result = extractor.extract_from_text(
            text=all_content,
            entities=entity_names,
        )

    # 格式化为 Markdown
    return format_watchlist_markdown(result)
