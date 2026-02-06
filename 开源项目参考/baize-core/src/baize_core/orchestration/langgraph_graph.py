"""LangGraph 编排实现。"""

from __future__ import annotations

from typing import TypedDict

from baize_core.orchestration.review import ReviewAgent
from baize_core.schemas.evidence import Artifact, Chunk, Claim, Evidence, Report
from baize_core.schemas.review import ReviewResult


class ReviewState(TypedDict):
    """审查状态。"""

    claims: list[Claim]
    evidence: list[Evidence]
    chunks: list[Chunk]
    artifacts: list[Artifact]
    report: Report | None
    review: ReviewResult | None


def build_review_graph(reviewer: ReviewAgent) -> object:
    """构建审查子图。"""

    try:
        from langgraph.graph import END, START, StateGraph
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 langgraph") from exc

    def review_node(state: ReviewState) -> ReviewState:
        result = reviewer.review(
            claims=state["claims"],
            evidence=state["evidence"],
            chunks=state["chunks"],
            artifacts=state["artifacts"],
            report=state.get("report"),
        )
        return {**state, "review": result}

    builder = StateGraph(ReviewState)
    builder.add_node("review", review_node)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)
    return builder.compile()
