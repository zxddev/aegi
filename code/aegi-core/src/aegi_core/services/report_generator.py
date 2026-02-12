# Author: msq
"""报告生成服务 — 把分析输出组装成结构化报告。

支持 5 种报告类型：briefing、ach_matrix、evidence_chain、narrative、quality。
每种类型有专用的 section 生成器，从 DB 拉数据，可选调用 LLM 生成摘要/建议。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.contracts.schemas import (
    ReportSectionV1,
    ReportType,
    ReportV1,
)
from aegi_core.db.models.assertion import Assertion
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.db.models.judgment import Judgment
from aegi_core.db.models.narrative import Narrative
from aegi_core.db.models.report import Report
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.infra.llm_client import LLMClient

logger = logging.getLogger(__name__)

# -- PLACEHOLDER_REPORT_CONTEXT


class _ReportContext:
    """内部上下文，持有 section 生成器需要的所有 case 数据。"""

    def __init__(
        self,
        case_uid: str,
        assertions: list[Any],
        hypotheses: list[Any],
        source_claims: list[Any],
        narratives: list[Any],
        judgments: list[Any],
    ) -> None:
        self.case_uid = case_uid
        self.assertions = assertions
        self.hypotheses = hypotheses
        self.source_claims = source_claims
        self.narratives = narratives
        self.judgments = judgments


async def _load_context(db: AsyncSession, case_uid: str) -> _ReportContext:
    """从 DB 加载 case 的所有产物。"""
    assertions = list(
        (await db.execute(sa.select(Assertion).where(Assertion.case_uid == case_uid)))
        .scalars()
        .all()
    )
    hypotheses = list(
        (await db.execute(sa.select(Hypothesis).where(Hypothesis.case_uid == case_uid)))
        .scalars()
        .all()
    )
    source_claims = list(
        (
            await db.execute(
                sa.select(SourceClaim).where(SourceClaim.case_uid == case_uid)
            )
        )
        .scalars()
        .all()
    )
    narratives = list(
        (await db.execute(sa.select(Narrative).where(Narrative.case_uid == case_uid)))
        .scalars()
        .all()
    )
    judgments = list(
        (await db.execute(sa.select(Judgment).where(Judgment.case_uid == case_uid)))
        .scalars()
        .all()
    )
    return _ReportContext(
        case_uid=case_uid,
        assertions=assertions,
        hypotheses=hypotheses,
        source_claims=source_claims,
        narratives=narratives,
        judgments=judgments,
    )


# -- Section 生成器 --------------------------------------------------------


async def _section_executive_summary(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """LLM 生成的执行摘要。"""
    assertion_lines = [
        f"- [{a.kind}] {a.value} (confidence: {a.confidence})"
        for a in ctx.assertions[:30]
    ]
    hyp_lines = [
        f"- {h.label} (confidence: {h.confidence})" for h in ctx.hypotheses[:10]
    ]
    evidence_text = "\n".join(assertion_lines) if assertion_lines else "No assertions."
    hyp_text = "\n".join(hyp_lines) if hyp_lines else "No hypotheses."

    if llm:
        prompt = (
            "You are a senior intelligence analyst writing an executive summary.\n"
            "Based on the following intelligence assertions and hypotheses, write a "
            "concise executive summary (3-5 paragraphs) suitable for decision-makers.\n\n"
            f"## Assertions ({len(ctx.assertions)} total)\n{evidence_text}\n\n"
            f"## Hypotheses ({len(ctx.hypotheses)} total)\n{hyp_text}\n\n"
            "Write the summary in clear, professional language. Highlight key findings, "
            "confidence levels, and areas of uncertainty."
        )
        try:
            result = await llm.invoke(prompt)
            return ReportSectionV1(
                name="executive_summary",
                title="Executive Summary",
                content=result["text"],
            )
        except Exception:
            logger.warning("LLM 执行摘要生成失败", exc_info=True)

    return ReportSectionV1(
        name="executive_summary",
        title="Executive Summary",
        content=f"Case contains {len(ctx.assertions)} assertions, "
        f"{len(ctx.hypotheses)} hypotheses, and "
        f"{len(ctx.source_claims)} source claims.",
    )


async def _section_key_findings(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """按置信度排序的 top assertions。"""
    sorted_a = sorted(
        ctx.assertions,
        key=lambda a: a.confidence or 0,
        reverse=True,
    )[:20]
    items = []
    for a in sorted_a:
        items.append(
            {
                "uid": a.uid,
                "kind": a.kind,
                "value": a.value,
                "confidence": a.confidence,
                "source_claim_count": len(a.source_claim_uids or []),
            }
        )

    md_lines = [
        "| # | Kind | Confidence | Sources |",
        "|---|------|-----------|---------|",
    ]
    for i, item in enumerate(items, 1):
        md_lines.append(
            f"| {i} | {item['kind']} | {item['confidence']:.2f} | {item['source_claim_count']} |"
        )

    return ReportSectionV1(
        name="key_findings",
        title="Key Findings",
        content="\n".join(md_lines),
        data={"items": items},
    )


# PLACEHOLDER_MORE_SECTIONS


async def _section_competing_hypotheses(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """假设列表，含支持/反对证据计数。"""
    items = []
    for h in ctx.hypotheses:
        supporting = len(h.supporting_assertion_uids or [])
        items.append(
            {
                "uid": h.uid,
                "label": h.label,
                "confidence": h.confidence,
                "supporting_count": supporting,
            }
        )

    md_lines = [
        "| Hypothesis | Confidence | Supporting Evidence |",
        "|-----------|-----------|-------------------|",
    ]
    for item in items:
        conf = f"{item['confidence']:.2f}" if item["confidence"] else "N/A"
        md_lines.append(
            f"| {item['label'][:80]} | {conf} | {item['supporting_count']} |"
        )

    return ReportSectionV1(
        name="competing_hypotheses",
        title="Competing Hypotheses",
        content="\n".join(md_lines),
        data={"items": items},
    )


async def _section_information_gaps(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """识别信息缺口和盲区。"""
    gaps: list[str] = []
    if len(ctx.source_claims) < 3:
        gaps.append("Limited source diversity — fewer than 3 source claims.")
    sources = {sc.attributed_to for sc in ctx.source_claims if sc.attributed_to}
    if len(sources) < 2:
        gaps.append(
            "Single-source dependency — evidence from fewer than 2 distinct sources."
        )
    if not ctx.hypotheses:
        gaps.append("No competing hypotheses generated.")
    low_conf = [a for a in ctx.assertions if (a.confidence or 0) < 0.3]
    if low_conf:
        gaps.append(f"{len(low_conf)} assertions with confidence below 0.3.")

    content = (
        "\n".join(f"- {g}" for g in gaps) if gaps else "No significant gaps identified."
    )
    return ReportSectionV1(
        name="information_gaps",
        title="Information Gaps",
        content=content,
        data={"gaps": gaps},
    )


async def _section_source_assessment(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """来源多样性和归属分析。"""
    sources: dict[str, int] = {}
    languages: dict[str, int] = {}
    for sc in ctx.source_claims:
        src = sc.attributed_to or "Unknown"
        sources[src] = sources.get(src, 0) + 1
        lang = sc.language or "unknown"
        languages[lang] = languages.get(lang, 0) + 1

    md_lines = ["### Sources", "| Source | Claims |", "|--------|--------|"]
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        md_lines.append(f"| {src} | {count} |")
    md_lines.extend(
        ["", "### Languages", "| Language | Claims |", "|----------|--------|"]
    )
    for lang, count in sorted(languages.items(), key=lambda x: -x[1]):
        md_lines.append(f"| {lang} | {count} |")

    return ReportSectionV1(
        name="source_assessment",
        title="Source Assessment",
        content="\n".join(md_lines),
        data={"sources": sources, "languages": languages},
    )


async def _section_recommendations(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """LLM 生成的建议。"""
    if llm:
        findings = "\n".join(f"- [{a.kind}] {a.value}" for a in ctx.assertions[:15])
        gaps_text = ""
        if len(ctx.source_claims) < 3:
            gaps_text += "- Limited source diversity\n"
        if not ctx.hypotheses:
            gaps_text += "- No competing hypotheses\n"

        prompt = (
            "You are a senior intelligence analyst. Based on the following findings "
            "and identified gaps, provide 3-5 actionable recommendations.\n\n"
            f"## Key Findings\n{findings}\n\n"
            f"## Gaps\n{gaps_text or 'None identified'}\n\n"
            "Format as a numbered list. Be specific and actionable."
        )
        try:
            result = await llm.invoke(prompt)
            return ReportSectionV1(
                name="recommendations",
                title="Recommendations",
                content=result["text"],
            )
        except Exception:
            logger.warning("LLM 建议生成失败", exc_info=True)

    return ReportSectionV1(
        name="recommendations",
        title="Recommendations",
        content="Recommendations require LLM analysis. Re-run with LLM enabled.",
    )


# -- ACH 矩阵 sections -------------------------------------------------------


async def _section_ach_matrix(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """ACH 矩阵：假设 × 证据。"""
    if not ctx.hypotheses or not ctx.assertions:
        return ReportSectionV1(
            name="ach_matrix",
            title="ACH Matrix",
            content="Insufficient data for ACH matrix.",
        )

    # 构建矩阵表头
    header = "| Evidence |"
    sep = "|----------|"
    for h in ctx.hypotheses[:10]:
        header += f" {h.label[:30]} |"
        sep += "----------|"

    rows = []
    for a in ctx.assertions[:30]:
        row = f"| {a.kind}: {str(a.value)[:40]} |"
        for h in ctx.hypotheses[:10]:
            if a.uid in (h.supporting_assertion_uids or []):
                row += " C |"
            else:
                row += " - |"
        rows.append(row)

    content = "\n".join([header, sep] + rows)
    return ReportSectionV1(
        name="ach_matrix",
        title="ACH Matrix",
        content=content,
    )


async def _section_hypothesis_rankings(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """按一致性评分排序的假设。"""
    sorted_h = sorted(
        ctx.hypotheses,
        key=lambda h: h.confidence or 0,
        reverse=True,
    )
    md_lines = [
        "| Rank | Hypothesis | Confidence |",
        "|------|-----------|-----------|",
    ]
    for i, h in enumerate(sorted_h, 1):
        conf = f"{h.confidence:.2f}" if h.confidence else "N/A"
        md_lines.append(f"| {i} | {h.label[:80]} | {conf} |")

    return ReportSectionV1(
        name="hypothesis_rankings",
        title="Hypothesis Rankings",
        content="\n".join(md_lines),
    )


# -- 证据链 sections ---------------------------------------------------


async def _section_timeline(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """Source claims 时间线。"""
    sorted_sc = sorted(ctx.source_claims, key=lambda sc: sc.created_at)
    md_lines = ["| Time | Source | Quote |", "|------|--------|-------|"]
    for sc in sorted_sc[:50]:
        ts = sc.created_at.strftime("%Y-%m-%d %H:%M") if sc.created_at else "?"
        src = sc.attributed_to or "Unknown"
        quote = (sc.quote or "")[:80]
        md_lines.append(f"| {ts} | {src} | {quote} |")

    return ReportSectionV1(
        name="timeline",
        title="Evidence Timeline",
        content="\n".join(md_lines),
    )


# -- 叙事 sections --------------------------------------------------------


async def _section_narrative_clusters(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """检测到的叙事聚类。"""
    if not ctx.narratives:
        return ReportSectionV1(
            name="narrative_clusters",
            title="Narrative Clusters",
            content="No narratives detected.",
        )
    md_lines = []
    for n in ctx.narratives:
        md_lines.append(f"### {n.title}")
        md_lines.append(f"- Assertions: {len(n.assertion_uids or [])}")
        md_lines.append(f"- Hypotheses: {len(n.hypothesis_uids or [])}")
        md_lines.append("")

    return ReportSectionV1(
        name="narrative_clusters",
        title="Narrative Clusters",
        content="\n".join(md_lines),
    )


# -- 质量 sections ----------------------------------------------------------


async def _section_confidence_score(
    ctx: _ReportContext,
    llm: LLMClient | None,
) -> ReportSectionV1:
    """整体置信度评估。"""
    if not ctx.assertions:
        return ReportSectionV1(
            name="confidence_score",
            title="Confidence Score",
            content="No assertions to score.",
        )
    avg_conf = sum(a.confidence or 0 for a in ctx.assertions) / len(ctx.assertions)
    return ReportSectionV1(
        name="confidence_score",
        title="Confidence Score",
        content=f"Average assertion confidence: **{avg_conf:.2f}**\n\n"
        f"Total assertions: {len(ctx.assertions)}\n"
        f"Total hypotheses: {len(ctx.hypotheses)}\n"
        f"Total source claims: {len(ctx.source_claims)}",
        data={"average_confidence": avg_conf},
    )


# -- 报告类型 → section 映射 ---------------------------------------------

_REPORT_SECTIONS: dict[str, list] = {
    ReportType.BRIEFING: [
        _section_executive_summary,
        _section_key_findings,
        _section_competing_hypotheses,
        _section_information_gaps,
        _section_source_assessment,
        _section_recommendations,
    ],
    ReportType.ACH_MATRIX: [
        _section_ach_matrix,
        _section_hypothesis_rankings,
        _section_key_findings,
        _section_information_gaps,
    ],
    ReportType.EVIDENCE_CHAIN: [
        _section_timeline,
        _section_source_assessment,
        _section_key_findings,
    ],
    ReportType.NARRATIVE: [
        _section_narrative_clusters,
        _section_key_findings,
        _section_source_assessment,
    ],
    ReportType.QUALITY: [
        _section_confidence_score,
        _section_information_gaps,
        _section_source_assessment,
        _section_recommendations,
    ],
}

_REPORT_TITLES: dict[str, str] = {
    ReportType.BRIEFING: "Intelligence Briefing",
    ReportType.ACH_MATRIX: "ACH Matrix Analysis",
    ReportType.EVIDENCE_CHAIN: "Evidence Chain Report",
    ReportType.NARRATIVE: "Narrative Analysis Report",
    ReportType.QUALITY: "Quality Assessment Report",
}


def _render_markdown(title: str, sections: list[ReportSectionV1]) -> str:
    """把 sections 渲染成单个 Markdown 文档。"""
    parts = [f"# {title}", ""]
    for sec in sections:
        parts.append(f"## {sec.title}")
        parts.append("")
        parts.append(sec.content)
        parts.append("")
    return "\n".join(parts)


# -- 主入口 ----------------------------------------------------------


class ReportGenerator:
    """从 case 分析数据生成结构化报告。"""

    async def generate(
        self,
        case_uid: str,
        report_type: str,
        *,
        sections_filter: list[str] | None = None,
        language: str = "en",
        db: AsyncSession,
        llm: LLMClient | None = None,
    ) -> ReportV1:
        ctx = await _load_context(db, case_uid)
        trace_id = f"report_{uuid4().hex}"

        section_fns = _REPORT_SECTIONS.get(report_type, [])
        if not section_fns:
            raise ValueError(f"Unknown report type: {report_type}")

        # 生成 sections
        sections: list[ReportSectionV1] = []
        for fn in section_fns:
            if (
                sections_filter
                and fn.__name__.replace("_section_", "") not in sections_filter
            ):
                continue
            try:
                sec = await fn(ctx, llm)
                sections.append(sec)
            except Exception:
                logger.warning("Section %s 生成失败", fn.__name__, exc_info=True)

        title = _REPORT_TITLES.get(report_type, "Report")
        rendered = _render_markdown(title, sections)

        # 持久化
        report_uid = f"rpt_{uuid4().hex[:12]}"
        db_report = Report(
            uid=report_uid,
            case_uid=case_uid,
            report_type=report_type,
            title=title,
            sections={
                "sections": [s.model_dump() for s in sections],
            },
            rendered_markdown=rendered,
            config={
                "language": language,
                "sections_filter": sections_filter,
            },
            trace_id=trace_id,
        )
        db.add(db_report)
        await db.commit()

        return ReportV1(
            uid=report_uid,
            case_uid=case_uid,
            report_type=report_type,
            title=title,
            sections=sections,
            rendered_markdown=rendered,
            config=db_report.config,
            trace_id=trace_id,
            created_at=db_report.created_at,
        )
