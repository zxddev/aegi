"""CrewAI 协作封装。

实现多 Agent 协作：
- Analyst: 事实分析与归纳
- Historian: 历史背景与趋势
- DomainExpert: 领域专业知识
- Strategist: 战略假设生成
- Critic: 批判性评估与缺口识别
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

from baize_core.llm.runner import LlmRunner
from baize_core.schemas.crew import CrewDecideSummary, CrewOrientSummary
from baize_core.schemas.policy import StageType

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Agent 角色。"""

    ANALYST = "analyst"
    HISTORIAN = "historian"
    DOMAIN_EXPERT = "domain_expert"
    STRATEGIST = "strategist"
    CRITIC = "critic"


# Agent 角色描述
AGENT_DESCRIPTIONS: dict[AgentRole, dict[str, str]] = {
    AgentRole.ANALYST: {
        "role": "事实分析师",
        "goal": "对收集的信息进行系统性分析，提取关键事实和模式",
        "backstory": "你是一位资深情报分析师，擅长从海量信息中提取关键事实，识别数据中的模式和异常。"
        "你的分析总是基于证据，避免主观臆断。",
    },
    AgentRole.HISTORIAN: {
        "role": "历史研究员",
        "goal": "提供历史背景和长期趋势分析",
        "backstory": "你是一位历史学者，专注于研究地缘政治和军事历史。"
        "你能够将当前事件置于历史背景中，识别历史模式和类比。",
    },
    AgentRole.DOMAIN_EXPERT: {
        "role": "领域专家",
        "goal": "提供专业领域知识和技术分析",
        "backstory": "你是一位军事和国防领域的专家，拥有深厚的专业知识。"
        "你能够解读技术细节，评估能力和意图。",
    },
    AgentRole.STRATEGIST: {
        "role": "战略分析师",
        "goal": "生成战略假设和情景分析",
        "backstory": "你是一位战略规划专家，擅长构建可检验的假设和情景。"
        "你的分析着眼于未来可能的发展方向和战略含义。",
    },
    AgentRole.CRITIC: {
        "role": "批判性评估员",
        "goal": "识别分析中的缺口、偏见和弱点",
        "backstory": "你是一位严谨的批判性思考者，专注于识别分析中的漏洞。"
        "你会挑战假设，指出证据不足之处，确保分析的稳健性。",
    },
}


# 简化版 prompts（用于 fallback）
ORIENT_SYSTEM_PROMPT = (
    "你是由 Analyst/Historian/DomainExpert 组成的协作小组。"
    "你的任务是对事实进行归纳、指出潜在冲突，并给出简要摘要。"
)

DECIDE_SYSTEM_PROMPT = (
    "你是由 Strategist/Critic 组成的协作小组。"
    "你的任务是给出若干假设与缺口清单，保持证据导向与审慎表述。"
)


@dataclass
class AgentOutput:
    """单个 Agent 的输出。"""

    role: AgentRole
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CrewExecutionResult:
    """Crew 执行结果。"""

    outputs: list[AgentOutput]
    final_output: str
    execution_time_ms: int = 0


class CrewBackend(ABC):
    """Crew 执行后端抽象。"""

    @abstractmethod
    async def execute_orient(self, context: str) -> CrewExecutionResult:
        """执行 Orient 阶段协作。"""

    @abstractmethod
    async def execute_decide(self, context: str) -> CrewExecutionResult:
        """执行 Decide 阶段协作。"""


class RealCrewAIBackend(CrewBackend):
    """真实 CrewAI 后端。

    使用 CrewAI 库创建多个 Agent 并协作执行任务。
    """

    def __init__(self, llm_model: str = "gpt-4") -> None:
        """初始化 CrewAI 后端。

        Args:
            llm_model: 使用的 LLM 模型
        """
        self._llm_model = llm_model
        self._crewai_available = _check_crewai_available()

    async def execute_orient(self, context: str) -> CrewExecutionResult:
        """执行 Orient 阶段协作。"""
        if not self._crewai_available:
            raise ImportError("CrewAI 未安装")

        import time

        from crewai import Agent, Crew, Task

        start_time = time.time()

        # 创建 Orient 阶段的 Agents
        analyst = Agent(
            role=AGENT_DESCRIPTIONS[AgentRole.ANALYST]["role"],
            goal=AGENT_DESCRIPTIONS[AgentRole.ANALYST]["goal"],
            backstory=AGENT_DESCRIPTIONS[AgentRole.ANALYST]["backstory"],
            verbose=True,
        )
        historian = Agent(
            role=AGENT_DESCRIPTIONS[AgentRole.HISTORIAN]["role"],
            goal=AGENT_DESCRIPTIONS[AgentRole.HISTORIAN]["goal"],
            backstory=AGENT_DESCRIPTIONS[AgentRole.HISTORIAN]["backstory"],
            verbose=True,
        )
        domain_expert = Agent(
            role=AGENT_DESCRIPTIONS[AgentRole.DOMAIN_EXPERT]["role"],
            goal=AGENT_DESCRIPTIONS[AgentRole.DOMAIN_EXPERT]["goal"],
            backstory=AGENT_DESCRIPTIONS[AgentRole.DOMAIN_EXPERT]["backstory"],
            verbose=True,
        )

        # 创建任务
        analysis_task = Task(
            description=f"分析以下情报信息，提取关键事实和模式：\n\n{context}",
            expected_output="关键事实列表和模式识别结果",
            agent=analyst,
        )
        history_task = Task(
            description="基于分析结果，提供历史背景和长期趋势分析",
            expected_output="历史背景分析和趋势识别",
            agent=historian,
            context=[analysis_task],
        )
        synthesis_task = Task(
            description="综合以上分析，生成最终摘要并指出任何冲突之处",
            expected_output="综合摘要和冲突列表",
            agent=domain_expert,
            context=[analysis_task, history_task],
        )

        # 创建并执行 Crew
        crew = Crew(
            agents=[analyst, historian, domain_expert],
            tasks=[analysis_task, history_task, synthesis_task],
            verbose=True,
        )

        # 在线程池中执行（CrewAI 是同步的）
        result = await asyncio.to_thread(crew.kickoff)

        elapsed_ms = int((time.time() - start_time) * 1000)

        return CrewExecutionResult(
            outputs=[
                AgentOutput(
                    role=AgentRole.ANALYST, content=str(analysis_task.output or "")
                ),
                AgentOutput(
                    role=AgentRole.HISTORIAN, content=str(history_task.output or "")
                ),
                AgentOutput(
                    role=AgentRole.DOMAIN_EXPERT,
                    content=str(synthesis_task.output or ""),
                ),
            ],
            final_output=str(result),
            execution_time_ms=elapsed_ms,
        )

    async def execute_decide(self, context: str) -> CrewExecutionResult:
        """执行 Decide 阶段协作。"""
        if not self._crewai_available:
            raise ImportError("CrewAI 未安装")

        import time

        from crewai import Agent, Crew, Task

        start_time = time.time()

        # 创建 Decide 阶段的 Agents
        strategist = Agent(
            role=AGENT_DESCRIPTIONS[AgentRole.STRATEGIST]["role"],
            goal=AGENT_DESCRIPTIONS[AgentRole.STRATEGIST]["goal"],
            backstory=AGENT_DESCRIPTIONS[AgentRole.STRATEGIST]["backstory"],
            verbose=True,
        )
        critic = Agent(
            role=AGENT_DESCRIPTIONS[AgentRole.CRITIC]["role"],
            goal=AGENT_DESCRIPTIONS[AgentRole.CRITIC]["goal"],
            backstory=AGENT_DESCRIPTIONS[AgentRole.CRITIC]["backstory"],
            verbose=True,
        )

        # 创建任务
        hypothesis_task = Task(
            description=f"基于以下分析，生成可检验的战略假设：\n\n{context}",
            expected_output="战略假设列表，每个假设都应该是可检验的",
            agent=strategist,
        )
        critique_task = Task(
            description="批判性评估以上假设，识别分析中的缺口和弱点",
            expected_output="缺口列表和改进建议",
            agent=critic,
            context=[hypothesis_task],
        )

        # 创建并执行 Crew
        crew = Crew(
            agents=[strategist, critic],
            tasks=[hypothesis_task, critique_task],
            verbose=True,
        )

        result = await asyncio.to_thread(crew.kickoff)

        elapsed_ms = int((time.time() - start_time) * 1000)

        return CrewExecutionResult(
            outputs=[
                AgentOutput(
                    role=AgentRole.STRATEGIST, content=str(hypothesis_task.output or "")
                ),
                AgentOutput(
                    role=AgentRole.CRITIC, content=str(critique_task.output or "")
                ),
            ],
            final_output=str(result),
            execution_time_ms=elapsed_ms,
        )


class LLMSimulatedBackend(CrewBackend):
    """LLM 模拟后端。

    使用单个 LLM 模拟多 Agent 协作（fallback）。
    """

    def __init__(self, llm_runner: LlmRunner) -> None:
        """初始化 LLM 模拟后端。

        Args:
            llm_runner: LLM 运行器
        """
        self._llm_runner = llm_runner

    async def execute_orient(self, context: str) -> CrewExecutionResult:
        """使用 LLM 模拟 Orient 协作。"""
        prompt = f"""你是由以下角色组成的协作小组：

1. 事实分析师：分析信息，提取关键事实和模式
2. 历史研究员：提供历史背景和长期趋势
3. 领域专家：提供专业知识和技术分析

请按角色顺序分析以下内容，然后给出综合摘要和冲突点：

{context}

请按以下格式输出：
【事实分析师】
<分析内容>

【历史研究员】
<分析内容>

【领域专家】
<综合分析>

【综合摘要】
<最终摘要>

【冲突点】
<冲突列表>"""

        result = await self._llm_runner.generate_text(
            system="你是一个模拟多Agent协作的系统。",
            user=prompt,
            stage=StageType.ORIENT,
            task_id="crew-simulated",
        )

        return CrewExecutionResult(
            outputs=[
                AgentOutput(role=AgentRole.ANALYST, content="模拟分析"),
                AgentOutput(role=AgentRole.HISTORIAN, content="模拟历史"),
                AgentOutput(role=AgentRole.DOMAIN_EXPERT, content="模拟专家"),
            ],
            final_output=result,
        )

    async def execute_decide(self, context: str) -> CrewExecutionResult:
        """使用 LLM 模拟 Decide 协作。"""
        prompt = f"""你是由以下角色组成的协作小组：

1. 战略分析师：生成可检验的战略假设
2. 批判性评估员：识别分析中的缺口和弱点

请按角色顺序分析以下内容：

{context}

请按以下格式输出：
【战略分析师】
<假设列表>

【批判性评估员】
<缺口列表>"""

        result = await self._llm_runner.generate_text(
            system="你是一个模拟多Agent协作的系统。",
            user=prompt,
            stage=StageType.DECIDE,
            task_id="crew-simulated",
        )

        return CrewExecutionResult(
            outputs=[
                AgentOutput(role=AgentRole.STRATEGIST, content="模拟假设"),
                AgentOutput(role=AgentRole.CRITIC, content="模拟批评"),
            ],
            final_output=result,
        )


@dataclass
class CrewCoordinator:
    """协作协调器。

    支持真实 CrewAI 后端和 LLM 模拟后端的自动切换。
    """

    llm_runner: LlmRunner
    use_real_crewai: bool = True  # 是否尝试使用真实 CrewAI

    def __post_init__(self) -> None:
        """初始化后端。"""
        self._real_backend: RealCrewAIBackend | None = None
        self._simulated_backend: LLMSimulatedBackend | None = None

        if self.use_real_crewai and _check_crewai_available():
            self._real_backend = RealCrewAIBackend()
            logger.info("使用真实 CrewAI 后端")
        else:
            logger.info("使用 LLM 模拟后端（CrewAI 不可用）")

    def _get_backend(self) -> CrewBackend:
        """获取可用后端。"""
        if self._real_backend is not None:
            return self._real_backend
        if self._simulated_backend is None:
            self._simulated_backend = LLMSimulatedBackend(self.llm_runner)
        return self._simulated_backend

    async def orient(self, *, context: str, task_id: str) -> CrewOrientSummary:
        """Orient 阶段协作输出。"""
        try:
            backend = self._get_backend()
            result = await backend.execute_orient(context)
            # 解析结果为结构化输出
            return await self._parse_orient_result(result, task_id)
        except Exception as e:
            logger.warning("Crew 执行失败，回退到简单 LLM: %s", e)
            return await self._fallback_orient(context, task_id)

    async def decide(self, *, context: str, task_id: str) -> CrewDecideSummary:
        """Decide 阶段协作输出。"""
        try:
            backend = self._get_backend()
            result = await backend.execute_decide(context)
            # 解析结果为结构化输出
            return await self._parse_decide_result(result, task_id)
        except Exception as e:
            logger.warning("Crew 执行失败，回退到简单 LLM: %s", e)
            return await self._fallback_decide(context, task_id)

    async def _parse_orient_result(
        self, result: CrewExecutionResult, task_id: str
    ) -> CrewOrientSummary:
        """解析 Orient 结果为结构化输出。"""
        # 使用 LLM 将 Crew 输出转换为结构化格式
        parse_prompt = f"""请将以下多Agent协作分析结果整理为JSON格式：

{result.final_output}

输出格式：
{{"summary": "综合摘要", "conflicts": ["冲突1", "冲突2"]}}"""

        structured_result = await self.llm_runner.generate_structured(
            system="你是一个输出格式化助手。",
            user=parse_prompt,
            schema=CrewOrientSummary,
            stage=StageType.ORIENT,
            task_id=task_id,
            max_retries=2,
        )
        return cast(CrewOrientSummary, structured_result.data)

    async def _parse_decide_result(
        self, result: CrewExecutionResult, task_id: str
    ) -> CrewDecideSummary:
        """解析 Decide 结果为结构化输出。"""
        parse_prompt = f"""请将以下多Agent协作分析结果整理为JSON格式：

{result.final_output}

输出格式：
{{"hypotheses": ["假设1", "假设2"], "gaps": ["缺口1", "缺口2"]}}"""

        structured_result = await self.llm_runner.generate_structured(
            system="你是一个输出格式化助手。",
            user=parse_prompt,
            schema=CrewDecideSummary,
            stage=StageType.DECIDE,
            task_id=task_id,
            max_retries=2,
        )
        return cast(CrewDecideSummary, structured_result.data)

    async def _fallback_orient(self, context: str, task_id: str) -> CrewOrientSummary:
        """Fallback: 使用简单 LLM 调用。"""
        result = await self.llm_runner.generate_structured(
            system=ORIENT_SYSTEM_PROMPT,
            user=context,
            schema=CrewOrientSummary,
            stage=StageType.ORIENT,
            task_id=task_id,
            max_retries=2,
        )
        return cast(CrewOrientSummary, result.data)

    async def _fallback_decide(self, context: str, task_id: str) -> CrewDecideSummary:
        """Fallback: 使用简单 LLM 调用。"""
        result = await self.llm_runner.generate_structured(
            system=DECIDE_SYSTEM_PROMPT,
            user=context,
            schema=CrewDecideSummary,
            stage=StageType.DECIDE,
            task_id=task_id,
            max_retries=2,
        )
        return cast(CrewDecideSummary, result.data)


def _check_crewai_available() -> bool:
    """检查 CrewAI 是否可用。"""
    try:
        importlib.import_module("crewai")
        return True
    except ImportError:
        return False


def _ensure_crewai_available() -> None:
    """确保 CrewAI 依赖可用。"""
    if not _check_crewai_available():
        raise ImportError("crewai 未安装。请运行: pip install crewai")
