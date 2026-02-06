"""快路径实现。

快路径用于简单查询场景，采用 ReAct 检索链，目标秒级响应。
与深路径（OODA 状态机）相比，快路径：
1. 不做多轮迭代
2. 不做反证与补洞
3. 证据不足直接拒答
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from baize_core.schemas.evidence import Artifact, Chunk, Evidence
from baize_core.schemas.task import TaskSpec


class FastPathState(TypedDict):
    """快路径状态。"""

    task: TaskSpec
    query: str
    evidence: list[Evidence]
    chunks: list[Chunk]
    artifacts: list[Artifact]
    answer: str | None
    confidence: float
    sources: list[str]
    completed: bool
    error: str | None


@dataclass
class FastPathResult:
    """快路径结果。

    Attributes:
        answer: 回答内容（证据不足时为 None）
        confidence: 置信度（0-1）
        sources: 来源列表
        evidence_count: 证据数量
        elapsed_ms: 耗时（毫秒）
        insufficient_evidence: 是否证据不足
    """

    answer: str | None
    confidence: float
    sources: list[str]
    evidence_count: int
    elapsed_ms: int
    insufficient_evidence: bool


# 快路径最小来源数量阈值
MIN_SOURCES_FOR_ANSWER = 2
# 快路径最小置信度阈值
MIN_CONFIDENCE_FOR_ANSWER = 0.3


def build_fast_path_graph() -> Any:
    """构建快路径图。

    快路径流程：
    1. search：执行搜索获取候选证据
    2. filter：过滤并评估证据质量
    3. answer：生成答案或拒答

    Returns:
        编译后的 LangGraph 子图
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 langgraph") from exc

    def search(state: FastPathState) -> FastPathState:
        """搜索阶段：从已有证据中检索相关内容。

        注意：实际搜索调用在外部完成，此处仅处理已有证据。
        """
        evidence = state.get("evidence", [])

        # 提取来源
        sources = list({e.source for e in evidence if e.source})

        return {
            **state,
            "sources": sources,
        }

    def filter_evidence(state: FastPathState) -> FastPathState:
        """过滤阶段：评估证据质量。

        根据可信度过滤低质量证据。
        """
        evidence = state.get("evidence", [])

        # 计算平均置信度
        if evidence:
            total_cred = sum(e.base_credibility for e in evidence)
            confidence = total_cred / len(evidence)
        else:
            confidence = 0.0

        return {
            **state,
            "confidence": confidence,
        }

    def answer(state: FastPathState) -> FastPathState:
        """回答阶段：生成答案或拒答。

        证据不足时直接拒答，不做猜测。
        """
        evidence = state.get("evidence", [])
        sources = state.get("sources", [])
        confidence = state.get("confidence", 0.0)
        chunks = state.get("chunks", [])

        # 检查是否满足回答条件
        insufficient = (
            len(sources) < MIN_SOURCES_FOR_ANSWER
            or confidence < MIN_CONFIDENCE_FOR_ANSWER
        )

        if insufficient:
            return {
                **state,
                "answer": None,
                "completed": True,
                "error": f"证据不足：来源数 {len(sources)}，置信度 {confidence:.2f}",
            }

        # 构建简要回答（基于证据摘要）
        summaries = []
        for evi in evidence[:5]:  # 最多取 5 条
            if evi.summary:
                summaries.append(f"- {evi.summary}")

        if summaries:
            answer_text = f"基于 {len(evidence)} 条证据的分析：\n" + "\n".join(
                summaries
            )
        else:
            # 使用 chunk 内容
            chunk_texts = []
            chunk_map = {c.chunk_uid: c for c in chunks}
            for evi in evidence[:3]:
                chunk = chunk_map.get(evi.chunk_uid)
                if chunk and chunk.text:
                    chunk_texts.append(chunk.text[:200])

            if chunk_texts:
                answer_text = f"基于 {len(evidence)} 条证据：\n" + "\n---\n".join(
                    chunk_texts
                )
            else:
                answer_text = f"找到 {len(evidence)} 条相关证据，但无法生成摘要。"

        return {
            **state,
            "answer": answer_text,
            "completed": True,
        }

    builder = StateGraph(FastPathState)
    builder.add_node("search", search)
    builder.add_node("filter", filter_evidence)
    builder.add_node("answer", answer)
    builder.add_edge(START, "search")
    builder.add_edge("search", "filter")
    builder.add_edge("filter", "answer")
    builder.add_edge("answer", END)
    return builder.compile()


async def run_fast_path(
    task: TaskSpec,
    evidence: list[Evidence],
    chunks: list[Chunk],
    artifacts: list[Artifact],
) -> FastPathResult:
    """执行快路径。

    Args:
        task: 任务规范
        evidence: 证据列表
        chunks: 切片列表
        artifacts: 工件列表

    Returns:
        快路径结果
    """
    import time

    start_time = time.time()

    graph = build_fast_path_graph()

    initial_state: FastPathState = {
        "task": task,
        "query": task.objective,
        "evidence": evidence,
        "chunks": chunks,
        "artifacts": artifacts,
        "answer": None,
        "confidence": 0.0,
        "sources": [],
        "completed": False,
        "error": None,
    }

    # 执行图
    result_state = await graph.ainvoke(initial_state)

    elapsed_ms = int((time.time() - start_time) * 1000)

    return FastPathResult(
        answer=result_state.get("answer"),
        confidence=result_state.get("confidence", 0.0),
        sources=result_state.get("sources", []),
        evidence_count=len(evidence),
        elapsed_ms=elapsed_ms,
        insufficient_evidence=result_state.get("answer") is None,
    )
