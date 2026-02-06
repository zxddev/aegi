"""HITL（Human-in-the-Loop）中断执行流程。

实现图执行中的暂停/恢复机制，支持真正的人在回路。

核心流程：
1. 图执行到达 HITL 中断点时暂停
2. 保存当前状态到检查点
3. 创建审查请求，等待人工决策
4. 人工决策后恢复执行
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from baize_core.orchestration.checkpoint import (
    CheckpointManager,
)
from baize_core.schemas.review_request import (
    ReviewCreateRequest,
    ReviewRequest,
    ReviewStatus,
)


class HitlTrigger(str, Enum):
    """HITL 触发类型。"""

    # 高风险工具调用
    HIGH_RISK_TOOL = "high_risk_tool"
    # 高成本操作
    HIGH_COST = "high_cost"
    # 建议级输出（需要人工确认）
    RECOMMENDATION_OUTPUT = "recommendation_output"
    # 策略引擎触发
    POLICY_REQUIRED = "policy_required"
    # 证据不足
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    # 冲突检测
    CONFLICT_DETECTED = "conflict_detected"
    # 显式请求
    EXPLICIT_REQUEST = "explicit_request"


class HitlInterruptPoint(BaseModel):
    """HITL 中断点定义。"""

    interrupt_id: str = Field(
        default_factory=lambda: f"int_{uuid4().hex[:12]}",
        description="中断点唯一标识",
    )
    thread_id: str = Field(description="线程/任务标识")
    step: str = Field(description="当前节点名称")
    trigger: HitlTrigger = Field(description="触发类型")
    reason: str = Field(description="中断原因")
    context: dict[str, Any] = Field(default_factory=dict, description="中断上下文")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="创建时间",
    )


class HitlResumeAction(str, Enum):
    """HITL 恢复动作。"""

    CONTINUE = "continue"  # 继续执行
    RETRY = "retry"  # 重试当前节点
    SKIP = "skip"  # 跳过当前节点
    ABORT = "abort"  # 中止执行
    ROLLBACK = "rollback"  # 回滚到指定检查点


class HitlResumeRequest(BaseModel):
    """HITL 恢复请求。"""

    interrupt_id: str = Field(description="中断点标识")
    action: HitlResumeAction = Field(description="恢复动作")
    reason: str | None = Field(default=None, description="决策原因")
    rollback_checkpoint_id: str | None = Field(
        default=None, description="回滚目标检查点（action=rollback 时必填）"
    )
    modified_state: dict[str, Any] | None = Field(
        default=None, description="修改后的状态（可选）"
    )
    decided_by: str | None = Field(default=None, description="决策人")
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="决策时间",
    )


class HitlSession(BaseModel):
    """HITL 会话状态。"""

    session_id: str = Field(
        default_factory=lambda: f"hitl_{uuid4().hex[:12]}",
        description="会话唯一标识",
    )
    thread_id: str = Field(description="线程/任务标识")
    checkpoint_id: str = Field(description="暂停时的检查点标识")
    interrupt: HitlInterruptPoint = Field(description="中断点信息")
    review_id: str | None = Field(default=None, description="关联的审查请求 ID")
    status: ReviewStatus = Field(default=ReviewStatus.PENDING, description="会话状态")
    resume_request: HitlResumeRequest | None = Field(
        default=None, description="恢复请求"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="创建时间",
    )
    resolved_at: datetime | None = Field(default=None, description="解决时间")


class HitlException(Exception):
    """HITL 中断异常。

    图执行遇到此异常时应暂停并等待人工决策。
    """

    def __init__(self, session: HitlSession) -> None:
        self.session = session
        super().__init__(f"HITL 中断: {session.interrupt.reason}")


@dataclass
class HitlManager:
    """HITL 管理器。

    管理中断点、暂停/恢复流程、审查请求关联。
    """

    checkpoint_manager: CheckpointManager
    # 审查请求创建回调
    create_review_callback: (
        Callable[[ReviewCreateRequest], Awaitable[ReviewRequest]] | None
    ) = None
    # 活跃的 HITL 会话（内存缓存）
    _sessions: dict[str, HitlSession] = field(default_factory=dict)
    # 按线程索引会话
    _thread_sessions: dict[str, list[str]] = field(default_factory=dict)

    async def create_interrupt(
        self,
        *,
        thread_id: str,
        state: dict[str, Any],
        step: str,
        trigger: HitlTrigger,
        reason: str,
        context: dict[str, Any] | None = None,
        auto_create_review: bool = True,
    ) -> HitlSession:
        """创建 HITL 中断。

        Args:
            thread_id: 线程/任务标识
            state: 当前状态
            step: 当前节点名称
            trigger: 触发类型
            reason: 中断原因
            context: 中断上下文
            auto_create_review: 是否自动创建审查请求

        Returns:
            HITL 会话
        """
        # 保存检查点
        checkpoint = await self.checkpoint_manager.save_state(
            thread_id=thread_id,
            state=state,
            step=step,
            metadata={
                "hitl_trigger": trigger.value,
                "hitl_reason": reason,
            },
        )

        # 创建中断点
        interrupt = HitlInterruptPoint(
            thread_id=thread_id,
            step=step,
            trigger=trigger,
            reason=reason,
            context=context or {},
        )

        # 创建会话
        session = HitlSession(
            thread_id=thread_id,
            checkpoint_id=checkpoint.checkpoint_id,
            interrupt=interrupt,
        )

        # 自动创建审查请求
        if auto_create_review and self.create_review_callback is not None:
            review = await self.create_review_callback(
                ReviewCreateRequest(
                    task_id=thread_id,
                    reason=reason,
                )
            )
            session.review_id = review.review_id

        # 保存会话
        self._sessions[session.session_id] = session
        if thread_id not in self._thread_sessions:
            self._thread_sessions[thread_id] = []
        self._thread_sessions[thread_id].append(session.session_id)

        return session

    async def get_session(self, session_id: str) -> HitlSession | None:
        """获取 HITL 会话。"""
        return self._sessions.get(session_id)

    async def get_pending_sessions(self, thread_id: str) -> list[HitlSession]:
        """获取指定线程的待处理会话。"""
        session_ids = self._thread_sessions.get(thread_id, [])
        return [
            self._sessions[sid]
            for sid in session_ids
            if sid in self._sessions
            and self._sessions[sid].status == ReviewStatus.PENDING
        ]

    async def resolve(
        self, session_id: str, resume_request: HitlResumeRequest
    ) -> tuple[HitlSession, dict[str, Any] | None]:
        """解决 HITL 中断。

        Args:
            session_id: 会话标识
            resume_request: 恢复请求

        Returns:
            (更新后的会话, 恢复的状态) 元组
            如果 action=abort 则状态为 None
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"会话不存在: {session_id}")
        if session.status != ReviewStatus.PENDING:
            raise ValueError(f"会话已解决: {session_id}")

        # 更新会话状态
        session.resume_request = resume_request
        session.resolved_at = datetime.now(UTC)

        # 根据动作类型决定状态
        if resume_request.action == HitlResumeAction.ABORT:
            session.status = ReviewStatus.REJECTED
            return session, None

        session.status = ReviewStatus.APPROVED

        # 获取恢复状态
        restored_state: dict[str, Any] | None = None

        if resume_request.action == HitlResumeAction.ROLLBACK:
            if resume_request.rollback_checkpoint_id is None:
                raise ValueError("回滚操作需要指定检查点")
            result = await self.checkpoint_manager.restore_from_checkpoint(
                resume_request.rollback_checkpoint_id
            )
            if result is None:
                raise ValueError("检查点不存在")
            restored_state, _ = result
        else:
            # CONTINUE, RETRY, SKIP: 从暂停时的检查点恢复
            result = await self.checkpoint_manager.restore_from_checkpoint(
                session.checkpoint_id
            )
            if result is None:
                raise ValueError("检查点不存在")
            restored_state, _ = result

        # 如果提供了修改后的状态，合并
        if resume_request.modified_state is not None:
            restored_state = {**restored_state, **resume_request.modified_state}

        return session, restored_state

    async def cleanup_thread(self, thread_id: str) -> int:
        """清理指定线程的所有会话。

        Args:
            thread_id: 线程标识

        Returns:
            清理的会话数量
        """
        session_ids = self._thread_sessions.pop(thread_id, [])
        count = 0
        for session_id in session_ids:
            if session_id in self._sessions:
                del self._sessions[session_id]
                count += 1
        return count


def create_hitl_interrupt_handler(
    hitl_manager: HitlManager,
    triggers: dict[str, HitlTrigger] | None = None,
) -> Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]]:
    """创建 HITL 中断处理器。

    用于在 LangGraph 节点中检查是否需要 HITL 中断。

    Args:
        hitl_manager: HITL 管理器
        triggers: 节点到触发类型的映射

    Returns:
        中断处理器函数
    """
    _triggers = triggers or {}

    async def handler(
        thread_id: str,
        state: dict[str, Any],
        step: str,
    ) -> dict[str, Any]:
        """检查并处理 HITL 中断。

        如果当前节点需要 HITL 中断，抛出 HitlException。
        否则返回原状态。
        """
        trigger = _triggers.get(step)
        if trigger is None:
            return state

        # 检查是否有待处理的会话
        pending = await hitl_manager.get_pending_sessions(thread_id)
        if pending:
            # 已有待处理会话，抛出异常
            raise HitlException(pending[0])

        # 创建新的中断
        session = await hitl_manager.create_interrupt(
            thread_id=thread_id,
            state=state,
            step=step,
            trigger=trigger,
            reason=f"节点 {step} 需要人工确认",
        )
        raise HitlException(session)

    return handler


async def run_with_hitl(
    graph: Any,
    initial_state: dict[str, Any],
    thread_id: str,
    hitl_manager: HitlManager,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """带 HITL 支持的图执行。

    如果遇到 HITL 中断，返回中断时的状态（包含 hitl_session 字段）。
    调用者应检查返回值中是否有 hitl_session 字段来判断是否需要等待人工决策。

    Args:
        graph: LangGraph 编译后的图
        initial_state: 初始状态
        thread_id: 线程标识
        hitl_manager: HITL 管理器
        config: 图执行配置

    Returns:
        最终状态或中断时的状态
    """
    current_state = initial_state
    config = config or {}
    config["configurable"] = config.get("configurable", {})
    config["configurable"]["thread_id"] = thread_id

    while True:
        try:
            result = await graph.ainvoke(current_state, config)
            return result
        except HitlException as e:
            # 返回中断状态，包含会话信息
            return {
                **current_state,
                "hitl_session": e.session.model_dump(),
                "hitl_interrupted": True,
            }


async def resume_from_hitl(
    graph: Any,
    session_id: str,
    resume_request: HitlResumeRequest,
    hitl_manager: HitlManager,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从 HITL 中断恢复执行。

    Args:
        graph: LangGraph 编译后的图
        session_id: HITL 会话标识
        resume_request: 恢复请求
        hitl_manager: HITL 管理器
        config: 图执行配置

    Returns:
        最终状态或新的中断状态
    """
    session, restored_state = await hitl_manager.resolve(session_id, resume_request)

    if restored_state is None:
        # 用户选择中止
        return {
            "hitl_aborted": True,
            "hitl_session": session.model_dump(),
        }

    config = config or {}
    config["configurable"] = config.get("configurable", {})
    config["configurable"]["thread_id"] = session.thread_id

    # 根据恢复动作决定起始节点
    if resume_request.action == HitlResumeAction.SKIP:
        # 跳过当前节点，从下一个节点开始
        # 这需要图支持 skip 语义，暂时用 continue 代替
        pass

    return await run_with_hitl(
        graph=graph,
        initial_state=restored_state,
        thread_id=session.thread_id,
        hitl_manager=hitl_manager,
        config=config,
    )
