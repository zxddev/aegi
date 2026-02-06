"""LangGraph Deep Agents Supervisor 模式。

实现顶层 Supervisor，负责：
- 任务规划与分解
- 子代理委托与调度
- 长短期记忆管理
- HITL 协调
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, Field

from baize_core.llm.runner import LlmRunner
from baize_core.orchestration.checkpoint import CheckpointManager
from baize_core.schemas.policy import StageType
from baize_core.schemas.task import TaskSpec


class SubtaskType(str, Enum):
    """子任务类型。"""

    RESEARCH = "research"  # 研究任务（STORM）
    ANALYSIS = "analysis"  # 分析任务（OODA）
    SYNTHESIS = "synthesis"  # 综合任务
    VALIDATION = "validation"  # 验证任务
    CUSTOM = "custom"  # 自定义任务


class SubtaskStatus(str, Enum):
    """子任务状态。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"  # 等待依赖


class Subtask(BaseModel):
    """子任务定义。"""

    subtask_id: str = Field(
        default_factory=lambda: f"sub_{uuid4().hex[:12]}",
        description="子任务唯一标识",
    )
    parent_task_id: str = Field(description="父任务标识")
    subtask_type: SubtaskType = Field(description="子任务类型")
    objective: str = Field(description="子任务目标")
    priority: int = Field(
        default=5, ge=1, le=10, description="优先级（1-10，越高越优先）"
    )
    dependencies: list[str] = Field(default_factory=list, description="依赖的子任务 ID")
    assigned_agent: str | None = Field(default=None, description="分配的代理")
    status: SubtaskStatus = Field(default=SubtaskStatus.PENDING)
    result: dict[str, Any] | None = Field(default=None, description="执行结果")
    error: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskPlan(BaseModel):
    """任务规划。"""

    plan_id: str = Field(
        default_factory=lambda: f"plan_{uuid4().hex[:12]}",
        description="规划唯一标识",
    )
    task_id: str = Field(description="任务标识")
    objective: str = Field(description="任务目标")
    subtasks: list[Subtask] = Field(default_factory=list, description="子任务列表")
    execution_order: list[str] = Field(
        default_factory=list, description="执行顺序（子任务 ID）"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    estimated_steps: int = Field(default=0, description="预估步骤数")


class SupervisorState(BaseModel):
    """Supervisor 状态。"""

    task: TaskSpec
    plan: TaskPlan | None = None
    current_subtask_id: str | None = None
    completed_subtasks: list[str] = Field(default_factory=list)
    failed_subtasks: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    iteration: int = 0
    max_iterations: int = 10


# 子代理类型
SubAgentHandler = Callable[[Subtask, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class Supervisor:
    """顶层 Supervisor。

    负责任务规划、子代理委托与调度。
    """

    llm_runner: LlmRunner
    checkpoint_manager: CheckpointManager | None = None

    # 子代理注册表
    _agents: dict[str, SubAgentHandler] = field(default_factory=dict)
    # 并发限制
    max_concurrent_subtasks: int = 3

    def register_agent(self, agent_type: str, handler: SubAgentHandler) -> None:
        """注册子代理。

        Args:
            agent_type: 代理类型（对应 SubtaskType）
            handler: 代理处理函数
        """
        self._agents[agent_type] = handler

    async def plan_task(self, task: TaskSpec) -> TaskPlan:
        """规划任务。

        将任务分解为子任务，确定执行顺序。

        Args:
            task: 任务规格

        Returns:
            任务规划
        """
        # 使用 LLM 进行任务规划
        planning_prompt = self._build_planning_prompt(task)
        planning_result = await self.llm_runner.generate_structured(
            system=PLANNING_SYSTEM_PROMPT,
            user=planning_prompt,
            schema=PlanningOutput,
            stage=StageType.PLANNING,
            task_id=task.task_id,
            max_retries=2,
        )

        # 转换为 TaskPlan
        planning_data = cast(PlanningOutput, planning_result.data)
        subtasks = []
        for item in planning_data.subtasks:
            subtask = Subtask(
                parent_task_id=task.task_id,
                subtask_type=_map_subtask_type(item.subtask_type),
                objective=item.objective,
                priority=item.priority,
                dependencies=item.dependencies,
            )
            subtasks.append(subtask)

        # 计算执行顺序（拓扑排序）
        execution_order = self._compute_execution_order(subtasks)

        plan = TaskPlan(
            task_id=task.task_id,
            objective=task.objective,
            subtasks=subtasks,
            execution_order=execution_order,
            estimated_steps=len(subtasks),
        )

        return plan

    async def execute_plan(
        self,
        task: TaskSpec,
        plan: TaskPlan | None = None,
    ) -> SupervisorState:
        """执行任务规划。

        Args:
            task: 任务规格
            plan: 任务规划（如果为 None，则自动规划）

        Returns:
            最终状态
        """
        if plan is None:
            plan = await self.plan_task(task)

        state = SupervisorState(
            task=task,
            plan=plan,
        )

        # 保存初始检查点
        if self.checkpoint_manager is not None:
            await self.checkpoint_manager.save_state(
                thread_id=task.task_id,
                state=state.model_dump(),
                step="plan",
            )

        # 按执行顺序执行子任务
        subtask_map = {s.subtask_id: s for s in plan.subtasks}
        results: dict[str, dict[str, Any]] = {}

        for subtask_id in plan.execution_order:
            if state.iteration >= state.max_iterations:
                break

            subtask = subtask_map.get(subtask_id)
            if subtask is None:
                continue

            # 检查依赖
            if not self._dependencies_satisfied(subtask, state.completed_subtasks):
                subtask.status = SubtaskStatus.BLOCKED
                continue

            state.current_subtask_id = subtask_id
            state.iteration += 1

            try:
                # 执行子任务
                result = await self._execute_subtask(subtask, results)
                subtask.status = SubtaskStatus.COMPLETED
                subtask.result = result
                subtask.completed_at = datetime.now(UTC)
                results[subtask_id] = result
                state.completed_subtasks.append(subtask_id)

            except Exception as e:
                subtask.status = SubtaskStatus.FAILED
                subtask.error = str(e)
                state.failed_subtasks.append(subtask_id)

            # 保存检查点
            if self.checkpoint_manager is not None:
                await self.checkpoint_manager.save_state(
                    thread_id=task.task_id,
                    state=state.model_dump(),
                    step=f"subtask_{subtask_id}",
                )

        state.context["results"] = results
        return state

    async def resume_execution(self, task_id: str) -> SupervisorState | None:
        """恢复执行。

        Args:
            task_id: 任务标识

        Returns:
            恢复后的状态，如果没有检查点则返回 None
        """
        if self.checkpoint_manager is None:
            return None

        saved_state = await self.checkpoint_manager.restore_state(task_id)
        if saved_state is None:
            return None

        state = SupervisorState.model_validate(saved_state)
        plan = state.plan

        if plan is None:
            return state

        # 继续执行未完成的子任务
        subtask_map = {s.subtask_id: s for s in plan.subtasks}
        results: dict[str, dict[str, Any]] = state.context.get("results", {})

        remaining = [
            sid
            for sid in plan.execution_order
            if sid not in state.completed_subtasks and sid not in state.failed_subtasks
        ]

        for subtask_id in remaining:
            if state.iteration >= state.max_iterations:
                break

            subtask = subtask_map.get(subtask_id)
            if subtask is None:
                continue

            if not self._dependencies_satisfied(subtask, state.completed_subtasks):
                continue

            state.current_subtask_id = subtask_id
            state.iteration += 1

            try:
                result = await self._execute_subtask(subtask, results)
                subtask.status = SubtaskStatus.COMPLETED
                subtask.result = result
                results[subtask_id] = result
                state.completed_subtasks.append(subtask_id)
            except Exception as e:
                subtask.status = SubtaskStatus.FAILED
                subtask.error = str(e)
                state.failed_subtasks.append(subtask_id)

            if self.checkpoint_manager is not None:
                await self.checkpoint_manager.save_state(
                    thread_id=state.task.task_id,
                    state=state.model_dump(),
                    step=f"subtask_{subtask_id}",
                )

        state.context["results"] = results
        return state

    async def _execute_subtask(
        self,
        subtask: Subtask,
        context: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """执行子任务。"""
        subtask.status = SubtaskStatus.IN_PROGRESS
        subtask.started_at = datetime.now(UTC)

        # 查找对应的代理
        agent_type = subtask.subtask_type.value
        handler = self._agents.get(agent_type)

        if handler is None:
            # 使用默认处理
            return await self._default_handler(subtask, context)

        return await handler(subtask, context)

    async def _default_handler(
        self,
        subtask: Subtask,
        context: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """默认子任务处理器。"""
        # 使用 LLM 处理
        execution_prompt = self._build_execution_prompt(subtask, context)
        result = await self.llm_runner.generate_text(
            system="你是任务执行代理，负责完成分配的子任务。",
            user=execution_prompt,
            stage=StageType.ACT,
            task_id=subtask.parent_task_id,
        )
        return {"output": result}

    def _build_planning_prompt(self, task: TaskSpec) -> str:
        """构建规划提示。"""
        return (
            f"任务目标：{task.objective}\n\n"
            "请将此任务分解为可执行的子任务，包括：\n"
            "1. 每个子任务的目标\n"
            "2. 子任务类型（research/analysis/synthesis/validation）\n"
            "3. 优先级（1-10）\n"
            "4. 依赖关系（哪些子任务必须先完成）\n"
        )

    def _build_execution_prompt(
        self,
        subtask: Subtask,
        context: dict[str, dict[str, Any]],
    ) -> str:
        """构建执行提示。"""
        context_summary = ""
        for dep_id in subtask.dependencies:
            if dep_id in context:
                dep_result = context[dep_id]
                context_summary += f"- 子任务 {dep_id} 结果：{str(dep_result)[:200]}\n"

        return (
            f"子任务目标：{subtask.objective}\n\n"
            f"上下文：\n{context_summary or '（无依赖结果）'}\n\n"
            "请执行此子任务并输出结果。"
        )

    def _compute_execution_order(self, subtasks: list[Subtask]) -> list[str]:
        """计算执行顺序（拓扑排序）。"""
        # 构建依赖图
        graph: dict[str, list[str]] = {}
        in_degree: dict[str, int] = {}

        for subtask in subtasks:
            sid = subtask.subtask_id
            graph[sid] = []
            in_degree[sid] = len(subtask.dependencies)

        for subtask in subtasks:
            for dep_id in subtask.dependencies:
                if dep_id in graph:
                    graph[dep_id].append(subtask.subtask_id)

        # 按优先级排序的队列
        queue = sorted(
            [s for s in subtasks if in_degree[s.subtask_id] == 0],
            key=lambda x: -x.priority,
        )
        order = []

        while queue:
            current = queue.pop(0)
            order.append(current.subtask_id)

            for next_id in graph[current.subtask_id]:
                in_degree[next_id] -= 1
                if in_degree[next_id] == 0:
                    next_subtask = next(
                        (s for s in subtasks if s.subtask_id == next_id), None
                    )
                    if next_subtask:
                        queue.append(next_subtask)
                        queue.sort(key=lambda x: -x.priority)

        return order

    def _dependencies_satisfied(
        self,
        subtask: Subtask,
        completed: list[str],
    ) -> bool:
        """检查依赖是否满足。"""
        return all(dep_id in completed for dep_id in subtask.dependencies)


# ==================== LLM 输出 Schema ====================


class PlanningSubtask(BaseModel):
    """规划子任务。"""

    objective: str = Field(description="子任务目标")
    subtask_type: str = Field(description="子任务类型")
    priority: int = Field(ge=1, le=10, description="优先级")
    dependencies: list[str] = Field(
        default_factory=list, description="依赖的子任务索引"
    )


class PlanningOutput(BaseModel):
    """规划输出。"""

    subtasks: list[PlanningSubtask] = Field(description="子任务列表")
    reasoning: str = Field(description="规划理由")


PLANNING_SYSTEM_PROMPT = """你是任务规划专家，负责将复杂任务分解为可执行的子任务。

规则：
1. 每个子任务必须有清晰的目标
2. 子任务类型：research（研究）、analysis（分析）、synthesis（综合）、validation（验证）
3. 优先级 1-10，10 最高
4. 依赖关系使用子任务索引（从 0 开始）
5. 确保子任务之间没有循环依赖"""


def _map_subtask_type(type_str: str) -> SubtaskType:
    """映射子任务类型。"""
    mapping = {
        "research": SubtaskType.RESEARCH,
        "analysis": SubtaskType.ANALYSIS,
        "synthesis": SubtaskType.SYNTHESIS,
        "validation": SubtaskType.VALIDATION,
    }
    return mapping.get(type_str.lower(), SubtaskType.CUSTOM)
