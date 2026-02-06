"""审计 Repository。

负责策略决策、工具调用、模型调用等审计记录的数据库操作。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import sqlalchemy
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from baize_core.schemas.audit import ModelTrace, PolicyDecisionRecord, ToolTrace
from baize_core.storage import models


@dataclass
class AuditRepository:
    """审计 Repository。

    Attributes:
        session_factory: SQLAlchemy 异步会话工厂
    """

    session_factory: async_sessionmaker[AsyncSession]

    # =========================================================================
    # 写入操作
    # =========================================================================

    async def record_policy_decision(self, record: PolicyDecisionRecord) -> None:
        """写入策略决策审计。

        Args:
            record: 策略决策记录
        """
        async with self.session_factory() as session:
            session.add(
                models.PolicyDecisionModel(
                    decision_id=record.decision_id,
                    request_id=record.request_id,
                    task_id=record.task_id,
                    action=record.action,
                    stage=record.stage,
                    allow=record.allow,
                    reason=record.reason,
                    enforced=record.enforced,
                    hitl=record.hitl,
                    created_at=record.created_at,
                    decided_at=record.decided_at or record.created_at,
                    hitl_required=record.hitl_required,
                )
            )
            await session.commit()

    async def record_tool_trace(self, trace: ToolTrace) -> None:
        """写入工具调用审计。

        使用 upsert 语义（ON CONFLICT DO NOTHING），避免与 MCP Gateway 双写冲突。

        Args:
            trace: 工具调用记录
        """
        from sqlalchemy.dialects.postgresql import insert

        async with self.session_factory() as session:
            stmt = insert(models.ToolTraceModel).values(
                trace_id=trace.trace_id,
                tool_name=trace.tool_name,
                task_id=trace.task_id,
                started_at=trace.started_at,
                duration_ms=trace.duration_ms,
                success=trace.success,
                error_type=trace.error_type,
                error_message=trace.error_message,
                result_ref=trace.result_ref,
                policy_decision_id=trace.policy_decision_id,
            ).on_conflict_do_nothing(index_elements=["trace_id"])
            await session.execute(stmt)
            await session.commit()

    async def record_model_trace(self, trace: ModelTrace) -> None:
        """写入模型调用审计。

        Args:
            trace: 模型调用记录
        """
        async with self.session_factory() as session:
            session.add(
                models.ModelTraceModel(
                    trace_id=trace.trace_id,
                    model=trace.model,
                    stage=trace.stage,
                    task_id=trace.task_id,
                    started_at=trace.started_at,
                    duration_ms=trace.duration_ms,
                    success=trace.success,
                    input_tokens=trace.input_tokens,
                    output_tokens=trace.output_tokens,
                    error_type=trace.error_type,
                    error_message=trace.error_message,
                    result_ref=trace.result_ref,
                    policy_decision_id=trace.policy_decision_id,
                )
            )
            await session.commit()

    # =========================================================================
    # 工具调用查询
    # =========================================================================

    async def query_tool_traces(
        self,
        *,
        task_id: str | None = None,
        tool_name: str | None = None,
        success: bool | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ToolTrace]:
        """查询工具调用记录。

        Args:
            task_id: 任务 ID 过滤
            tool_name: 工具名称过滤
            success: 成功状态过滤
            start_time: 开始时间过滤
            end_time: 结束时间过滤
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            工具调用记录列表
        """
        async with self.session_factory() as session:
            query = select(models.ToolTraceModel)
            if task_id:
                query = query.where(models.ToolTraceModel.task_id == task_id)
            if tool_name:
                query = query.where(models.ToolTraceModel.tool_name == tool_name)
            if success is not None:
                query = query.where(models.ToolTraceModel.success == success)
            if start_time:
                query = query.where(models.ToolTraceModel.started_at >= start_time)
            if end_time:
                query = query.where(models.ToolTraceModel.started_at <= end_time)
            query = query.order_by(models.ToolTraceModel.started_at.desc())
            query = query.limit(limit).offset(offset)
            result = await session.execute(query)
            rows = result.scalars().all()
            return [self._to_tool_trace(row) for row in rows]

    async def list_tool_traces_by_task(self, task_id: str) -> list[ToolTrace]:
        """按任务读取全部工具调用记录。

        Args:
            task_id: 任务 ID

        Returns:
            工具调用记录列表
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.ToolTraceModel)
                .where(models.ToolTraceModel.task_id == task_id)
                .order_by(models.ToolTraceModel.started_at.desc())
            )
            rows = result.scalars().all()
            return [self._to_tool_trace(row) for row in rows]

    async def query_tool_traces_by_policy_decision_id(
        self, decision_id: str
    ) -> list[ToolTrace]:
        """按策略决策 ID 查询工具调用记录。

        Args:
            decision_id: 策略决策 ID

        Returns:
            工具调用记录列表
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.ToolTraceModel)
                .where(models.ToolTraceModel.policy_decision_id == decision_id)
                .order_by(models.ToolTraceModel.started_at.desc())
            )
            rows = result.scalars().all()
            return [self._to_tool_trace(row) for row in rows]

    async def get_tool_trace(self, trace_id: str) -> ToolTrace | None:
        """获取单个工具调用记录。

        Args:
            trace_id: 调用记录 ID

        Returns:
            工具调用记录，不存在时返回 None
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.ToolTraceModel).where(
                    models.ToolTraceModel.trace_id == trace_id
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._to_tool_trace(row)

    # =========================================================================
    # 模型调用查询
    # =========================================================================

    async def query_model_traces(
        self,
        *,
        task_id: str | None = None,
        model_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ModelTrace]:
        """查询模型调用记录。

        Args:
            task_id: 任务 ID 过滤
            model_name: 模型名称过滤
            start_time: 开始时间过滤
            end_time: 结束时间过滤
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            模型调用记录列表
        """
        async with self.session_factory() as session:
            query = select(models.ModelTraceModel)
            if task_id:
                query = query.where(models.ModelTraceModel.task_id == task_id)
            if model_name:
                query = query.where(models.ModelTraceModel.model == model_name)
            if start_time:
                query = query.where(models.ModelTraceModel.started_at >= start_time)
            if end_time:
                query = query.where(models.ModelTraceModel.started_at <= end_time)
            query = query.order_by(models.ModelTraceModel.started_at.desc())
            query = query.limit(limit).offset(offset)
            result = await session.execute(query)
            rows = result.scalars().all()
            return [self._to_model_trace(row) for row in rows]

    async def get_model_trace(self, trace_id: str) -> ModelTrace | None:
        """获取单个模型调用记录。

        Args:
            trace_id: 调用记录 ID

        Returns:
            模型调用记录，不存在时返回 None
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.ModelTraceModel).where(
                    models.ModelTraceModel.trace_id == trace_id
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._to_model_trace(row)

    # =========================================================================
    # 策略决策查询
    # =========================================================================

    async def query_policy_decisions(
        self,
        *,
        task_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PolicyDecisionRecord]:
        """查询策略决策记录。

        Args:
            task_id: 任务 ID 过滤
            start_time: 开始时间过滤
            end_time: 结束时间过滤
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            策略决策记录列表
        """
        async with self.session_factory() as session:
            query = select(models.PolicyDecisionModel)
            if task_id:
                query = query.where(models.PolicyDecisionModel.task_id == task_id)
            if start_time:
                query = query.where(models.PolicyDecisionModel.decided_at >= start_time)
            if end_time:
                query = query.where(models.PolicyDecisionModel.decided_at <= end_time)
            query = query.order_by(models.PolicyDecisionModel.decided_at.desc())
            query = query.limit(limit).offset(offset)
            result = await session.execute(query)
            rows = result.scalars().all()
            return [
                PolicyDecisionRecord(
                    decision_id=row.decision_id,
                    request_id=row.request_id,
                    action=row.action,
                    stage=row.stage,
                    task_id=row.task_id or "",
                    allow=row.allow,
                    reason=row.reason,
                    enforced=row.enforced or {},
                    hitl=row.hitl or {},
                    hitl_required=row.hitl_required,
                    created_at=row.created_at,
                    decided_at=row.decided_at,
                )
                for row in rows
            ]

    # =========================================================================
    # 统计查询
    # =========================================================================

    async def get_tool_trace_stats(
        self,
        *,
        task_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """获取工具调用统计。

        Args:
            task_id: 任务 ID 过滤
            start_time: 开始时间过滤
            end_time: 结束时间过滤

        Returns:
            统计数据字典
        """
        async with self.session_factory() as session:
            query = select(
                func.count(models.ToolTraceModel.id).label("total"),
                func.sum(
                    func.cast(models.ToolTraceModel.success, sqlalchemy.Integer)
                ).label("success"),
                models.ToolTraceModel.tool_name,
                models.ToolTraceModel.error_type,
            ).group_by(
                models.ToolTraceModel.tool_name, models.ToolTraceModel.error_type
            )
            if task_id:
                query = query.where(models.ToolTraceModel.task_id == task_id)
            if start_time:
                query = query.where(models.ToolTraceModel.started_at >= start_time)
            if end_time:
                query = query.where(models.ToolTraceModel.started_at <= end_time)
            result = await session.execute(query)
            rows = result.all()

            total = 0
            success = 0
            by_tool: dict[str, int] = {}
            by_error: dict[str, int] = {}

            for row in rows:
                row_total = row.total or 0
                row_success = row.success or 0
                total += row_total
                success += row_success

                tool_name = row.tool_name or "unknown"
                by_tool[tool_name] = by_tool.get(tool_name, 0) + row_total

                if row.error_type:
                    by_error[row.error_type] = by_error.get(row.error_type, 0) + (
                        row_total - row_success
                    )

            return {
                "total": total,
                "success": success,
                "failed": total - success,
                "by_tool": by_tool,
                "by_error": by_error,
            }

    async def get_model_trace_stats(
        self,
        *,
        task_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """获取模型调用统计。

        Args:
            task_id: 任务 ID 过滤
            start_time: 开始时间过滤
            end_time: 结束时间过滤

        Returns:
            统计数据字典
        """
        async with self.session_factory() as session:
            query = select(
                func.count(models.ModelTraceModel.id).label("total"),
                func.sum(
                    func.cast(models.ModelTraceModel.success, sqlalchemy.Integer)
                ).label("success"),
                func.sum(models.ModelTraceModel.input_tokens).label("input_tokens"),
                func.sum(models.ModelTraceModel.output_tokens).label("output_tokens"),
                models.ModelTraceModel.model,
            ).group_by(models.ModelTraceModel.model)
            if task_id:
                query = query.where(models.ModelTraceModel.task_id == task_id)
            if start_time:
                query = query.where(models.ModelTraceModel.started_at >= start_time)
            if end_time:
                query = query.where(models.ModelTraceModel.started_at <= end_time)
            result = await session.execute(query)
            rows = result.all()

            total = 0
            success = 0
            input_tokens = 0
            output_tokens = 0
            by_model: dict[str, int] = {}

            for row in rows:
                row_total = row.total or 0
                row_success = row.success or 0
                total += row_total
                success += row_success
                input_tokens += row.input_tokens or 0
                output_tokens += row.output_tokens or 0

                model = row.model or "unknown"
                by_model[model] = by_model.get(model, 0) + row_total

            return {
                "total": total,
                "success": success,
                "failed": total - success,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "by_model": by_model,
            }

    async def get_policy_decision_stats(
        self,
        *,
        task_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """获取策略决策统计。

        Args:
            task_id: 任务 ID 过滤
            start_time: 开始时间过滤
            end_time: 结束时间过滤

        Returns:
            统计数据字典
        """
        async with self.session_factory() as session:
            query = select(
                func.count(models.PolicyDecisionModel.id).label("total"),
                func.sum(
                    func.cast(models.PolicyDecisionModel.allow, sqlalchemy.Integer)
                ).label("allows"),
            )
            if task_id:
                query = query.where(models.PolicyDecisionModel.task_id == task_id)
            if start_time:
                query = query.where(models.PolicyDecisionModel.decided_at >= start_time)
            if end_time:
                query = query.where(models.PolicyDecisionModel.decided_at <= end_time)
            result = await session.execute(query)
            row = result.one()

            total = row.total or 0
            allows = row.allows or 0

            return {
                "total": total,
                "allows": allows,
                "denies": total - allows,
            }

    # =========================================================================
    # 辅助方法
    # =========================================================================

    @staticmethod
    def _to_tool_trace(row: models.ToolTraceModel) -> ToolTrace:
        """转换工具调用记录。"""
        return ToolTrace(
            trace_id=row.trace_id,
            tool_name=row.tool_name,
            task_id=row.task_id or "",
            started_at=row.started_at,
            duration_ms=row.duration_ms,
            success=row.success,
            error_type=row.error_type,
            error_message=row.error_message,
            result_ref=row.result_ref,
            policy_decision_id=row.policy_decision_id,
        )

    @staticmethod
    def _to_model_trace(row: models.ModelTraceModel) -> ModelTrace:
        """转换模型调用记录。"""
        return ModelTrace(
            trace_id=row.trace_id,
            model=row.model,
            stage=row.stage,
            task_id=row.task_id or "",
            started_at=row.started_at,
            duration_ms=row.duration_ms,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            success=row.success,
            error_type=row.error_type,
            error_message=row.error_message,
            result_ref=row.result_ref,
            policy_decision_id=row.policy_decision_id,
        )
