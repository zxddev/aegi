"""基于 Z3 的约束校验器。"""

from __future__ import annotations

import importlib.util
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from baize_core.validation.constraints_types import (
    DEFAULT_CAUSALITY_RULES,
    DEFAULT_MUTEX_STATES,
    CausalityRule,
    ConstraintType,
    ConstraintValidator,
    ConstraintViolation,
    MutexState,
    TimelineEvent,
    ValidationReport,
    ValidationResult,
)

logger = logging.getLogger(__name__)

_EPOCH_MAX = 253402300799  # 9999-12-31T23:59:59Z


def _to_epoch_seconds(dt: datetime) -> int:
    """将 datetime 统一转换为 UTC epoch seconds（兼容 naive/aware）。"""
    if dt.tzinfo is None:
        # 兼容历史代码：将 naive 当作 UTC
        return int(dt.replace(tzinfo=UTC).timestamp())
    return int(dt.astimezone(UTC).timestamp())


class Z3ConstraintValidator(ConstraintValidator):
    """基于 Z3 的约束校验器。

    使用 Z3 SMT 求解器进行形式化约束验证。
    """

    def __init__(self) -> None:
        """初始化 Z3 校验器。"""
        self._z3_available = self._check_z3_available()

    def _check_z3_available(self) -> bool:
        """检查 Z3 是否可用。"""
        return importlib.util.find_spec("z3") is not None

    def validate(self, constraints: list[dict[str, Any]]) -> ValidationReport:
        """使用 Z3 校验约束。"""
        if not self._z3_available:
            logger.warning("Z3 未安装，使用简化校验")
            return self._simplified_validate(constraints)

        import z3

        violations: list[ConstraintViolation] = []
        checked = 0

        # 创建 Z3 求解器
        solver = z3.Solver()

        for constraint in constraints:
            checked += 1
            try:
                # 解析约束
                expr = self._parse_constraint(constraint)
                if expr is not None:
                    # 添加约束的否定，检查是否可满足
                    solver.push()
                    solver.add(z3.Not(expr))
                    result = solver.check()
                    solver.pop()

                    if result == z3.sat:
                        # 存在反例，约束可能被违反
                        model = solver.model()
                        violations.append(
                            ConstraintViolation(
                                constraint_type=ConstraintType(
                                    constraint.get("type", "range")
                                ),
                                message=f"约束可能被违反: {constraint.get('expression', '')}",
                                evidence=[str(model)],
                                severity="warning",
                            )
                        )
            except Exception as exc:
                logger.warning("约束解析失败: %s", exc)

        result = ValidationResult.VALID if not violations else ValidationResult.INVALID
        return ValidationReport(
            result=result,
            violations=violations,
            checked_constraints=checked,
            passed_constraints=checked - len(violations),
        )

    def _parse_constraint(self, constraint: dict[str, Any]) -> Any:
        """解析约束表达式为 Z3 表达式。"""
        import z3

        variables = constraint.get("variables", {})
        expression = constraint.get("expression", "")

        # 创建 Z3 变量
        z3_vars: dict[str, Any] = {}
        for name, var_type in variables.items():
            if var_type == "int":
                z3_vars[name] = z3.Int(name)
            elif var_type == "real":
                z3_vars[name] = z3.Real(name)
            elif var_type == "bool":
                z3_vars[name] = z3.Bool(name)

        # 简单表达式解析（实际应该使用更完整的解析器）
        if ">=" in expression:
            parts = expression.split(">=")
            if len(parts) == 2:
                left = parts[0].strip()
                right = int(parts[1].strip())
                if left in z3_vars:
                    return z3_vars[left] >= right
        elif "<=" in expression:
            parts = expression.split("<=")
            if len(parts) == 2:
                left = parts[0].strip()
                right = int(parts[1].strip())
                if left in z3_vars:
                    return z3_vars[left] <= right

        return None

    def _simplified_validate(
        self, constraints: list[dict[str, Any]]
    ) -> ValidationReport:
        """简化的约束校验（不使用 Z3）。"""
        return ValidationReport(
            result=ValidationResult.UNKNOWN,
            violations=[
                ConstraintViolation(
                    constraint_type=ConstraintType.RANGE,
                    message="Z3 未安装，无法进行形式化验证",
                    severity="warning",
                )
            ],
            checked_constraints=len(constraints),
            passed_constraints=0,
        )


# 审计回调类型
AuditCallback = Callable[[ValidationReport, list[TimelineEvent], int], None]


class Z3EventTimelineValidator:
    """基于 Z3 的事件时间线校验器。

    执行形式化约束验证：
    1. 事件时序约束：event_a.time_end <= event_b.time_start
    2. 资源互斥：同一实体不能同时处于冲突状态
    3. 因果关系：部署事件必须早于作战事件
    """

    def __init__(
        self,
        causality_rules: list[CausalityRule] | None = None,
        mutex_states: list[MutexState] | None = None,
        audit_callback: AuditCallback | None = None,
    ) -> None:
        """初始化 Z3 事件时间线校验器。"""
        self._causality_rules = causality_rules or DEFAULT_CAUSALITY_RULES
        self._mutex_states = mutex_states or DEFAULT_MUTEX_STATES
        self._z3_available = self._check_z3_available()
        self._audit_callback = audit_callback

    def _check_z3_available(self) -> bool:
        """检查 Z3 是否可用。"""
        try:
            import z3  # noqa: F401

            return True
        except ImportError:
            logger.warning("Z3 未安装，使用简化校验模式")
            return False

    def validate_events(
        self,
        events: list[TimelineEvent],
    ) -> ValidationReport:
        """校验事件时间线。"""
        start_time = time.monotonic()
        violations: list[ConstraintViolation] = []
        checked = 0

        # 1. 时序约束校验
        time_violations, time_checked = self._validate_time_sequence(events)
        violations.extend(time_violations)
        checked += time_checked

        # 2. 因果关系校验
        causal_violations, causal_checked = self._validate_causality(events)
        violations.extend(causal_violations)
        checked += causal_checked

        # 3. 互斥状态校验
        mutex_violations, mutex_checked = self._validate_mutex_states(events)
        violations.extend(mutex_violations)
        checked += mutex_checked

        # 4. 如果 Z3 可用，进行形式化验证
        if self._z3_available and events:
            z3_violations, z3_checked = self._z3_formal_verify(events)
            violations.extend(z3_violations)
            checked += z3_checked

        result = ValidationResult.VALID if not violations else ValidationResult.INVALID
        report = ValidationReport(
            result=result,
            violations=violations,
            checked_constraints=checked,
            passed_constraints=checked - len(violations),
        )

        # 5. 审计记录回调
        duration_ms = int((time.monotonic() - start_time) * 1000)
        if self._audit_callback is not None:
            self._audit_callback(report, events, duration_ms)

        return report

    def _validate_time_sequence(
        self,
        events: list[TimelineEvent],
    ) -> tuple[list[ConstraintViolation], int]:
        """校验事件时间序列约束。"""
        violations: list[ConstraintViolation] = []
        checked = 0

        # 按实体分组
        entity_events: dict[str, list[TimelineEvent]] = {}
        for event in events:
            for entity in event.entities:
                if entity not in entity_events:
                    entity_events[entity] = []
                entity_events[entity].append(event)

        # 校验每个实体的事件时序
        for entity, entity_event_list in entity_events.items():
            sorted_events = sorted(entity_event_list, key=lambda e: e.timestamp)
            checked += 1

            for i in range(len(sorted_events) - 1):
                current = sorted_events[i]
                next_event = sorted_events[i + 1]

                # 检查时间重叠
                if current.time_end and _to_epoch_seconds(
                    current.time_end
                ) > _to_epoch_seconds(next_event.timestamp):
                    violations.append(
                        ConstraintViolation(
                            constraint_type=ConstraintType.TIMELINE,
                            message=(
                                f"事件时间重叠：实体 '{entity}' 的事件 "
                                f"'{current.event_id}' 结束时间 ({current.time_end}) "
                                f"晚于 事件 '{next_event.event_id}' 开始时间 "
                                f"({next_event.timestamp})"
                            ),
                            evidence=[
                                f"事件A: {current.description} (结束: {current.time_end})",
                                f"事件B: {next_event.description} (开始: {next_event.timestamp})",
                            ],
                            severity="error",
                        )
                    )

        return violations, checked

    def _validate_causality(
        self,
        events: list[TimelineEvent],
    ) -> tuple[list[ConstraintViolation], int]:
        """校验因果关系约束。"""
        violations: list[ConstraintViolation] = []
        checked = 0

        # 按事件类型分组
        events_by_type: dict[str, list[TimelineEvent]] = {}
        for event in events:
            if event.event_type:
                if event.event_type not in events_by_type:
                    events_by_type[event.event_type] = []
                events_by_type[event.event_type].append(event)

        # 校验每条因果规则
        for rule in self._causality_rules:
            checked += 1
            cause_events = events_by_type.get(rule.cause_type, [])
            effect_events = events_by_type.get(rule.effect_type, [])

            if not cause_events or not effect_events:
                continue

            # 检查是否有 effect 事件早于所有 cause 事件
            earliest_cause_dt = min(
                cause_events, key=lambda e: _to_epoch_seconds(e.timestamp)
            ).timestamp
            earliest_cause = _to_epoch_seconds(earliest_cause_dt)
            for effect in effect_events:
                if _to_epoch_seconds(effect.timestamp) < earliest_cause:
                    violations.append(
                        ConstraintViolation(
                            constraint_type=ConstraintType.IMPLICATION,
                            message=f"因果关系违反：{rule.description}",
                            evidence=[
                                f"最早的 '{rule.cause_type}' 事件: {earliest_cause_dt}",
                                f"'{rule.effect_type}' 事件: {effect.description} ({effect.timestamp})",
                            ],
                            severity="error",
                        )
                    )

        return violations, checked

    def _validate_mutex_states(
        self,
        events: list[TimelineEvent],
    ) -> tuple[list[ConstraintViolation], int]:
        """校验互斥状态约束。"""
        violations: list[ConstraintViolation] = []
        checked = 0

        # 构建实体状态时间线
        entity_states: dict[str, list[tuple[datetime, datetime | None, str, str]]] = {}
        for event in events:
            if not event.state:
                continue
            for entity in event.entities:
                if entity not in entity_states:
                    entity_states[entity] = []
                entity_states[entity].append(
                    (
                        event.timestamp,
                        event.time_end,
                        event.state,
                        event.event_id,
                    )
                )

        # 校验每条互斥规则
        for rule in self._mutex_states:
            checked += 1
            for entity, states in entity_states.items():
                # 检查是否有时间重叠的互斥状态
                for i, (start_a, end_a, state_a, id_a) in enumerate(states):
                    for start_b, end_b, state_b, id_b in states[i + 1 :]:
                        if state_a == rule.state_a and state_b == rule.state_b:
                            # 检查时间是否重叠
                            if self._time_overlaps(start_a, end_a, start_b, end_b):
                                violations.append(
                                    ConstraintViolation(
                                        constraint_type=ConstraintType.MUTEX,
                                        message=(
                                            f"互斥状态违反：实体 '{entity}' "
                                            f"同时处于 '{state_a}' 和 '{state_b}' 状态"
                                        ),
                                        evidence=[
                                            f"状态 '{state_a}': 事件 {id_a} ({start_a} - {end_a or '持续'})",
                                            f"状态 '{state_b}': 事件 {id_b} ({start_b} - {end_b or '持续'})",
                                        ],
                                        severity="error",
                                    )
                                )

        return violations, checked

    def _time_overlaps(
        self,
        start_a: datetime,
        end_a: datetime | None,
        start_b: datetime,
        end_b: datetime | None,
    ) -> bool:
        """检查两个时间区间是否重叠。"""
        # 如果没有结束时间，假设持续到无穷远
        start_a_s = _to_epoch_seconds(start_a)
        start_b_s = _to_epoch_seconds(start_b)
        effective_end_a_s = _to_epoch_seconds(end_a) if end_a else _EPOCH_MAX
        effective_end_b_s = _to_epoch_seconds(end_b) if end_b else _EPOCH_MAX
        return start_a_s < effective_end_b_s and start_b_s < effective_end_a_s

    def _z3_formal_verify(
        self,
        events: list[TimelineEvent],
    ) -> tuple[list[ConstraintViolation], int]:
        """使用 Z3 进行形式化验证。"""
        import z3

        violations: list[ConstraintViolation] = []
        checked = 0

        solver = z3.Solver()

        # 为每个事件创建时间变量
        event_vars: dict[str, tuple[z3.ArithRef, z3.ArithRef]] = {}
        for event in events:
            start_var = z3.Int(f"{event.event_id}_start")
            end_var = z3.Int(f"{event.event_id}_end")
            event_vars[event.event_id] = (start_var, end_var)

            # 添加基本约束：start <= end
            solver.add(start_var <= end_var)

            # 添加时间值约束
            timestamp_int = _to_epoch_seconds(event.timestamp)
            solver.add(start_var == timestamp_int)
            if event.time_end:
                end_timestamp_int = _to_epoch_seconds(event.time_end)
                solver.add(end_var == end_timestamp_int)

        # 显式相对时序约束（可选）：metadata.after / metadata.before
        for event in events:
            start_var, _ = event_vars[event.event_id]
            after_ids = (
                event.metadata.get("after")
                if isinstance(event.metadata, dict)
                else None
            )
            if isinstance(after_ids, list):
                for other_id in after_ids:
                    if isinstance(other_id, str) and other_id in event_vars:
                        _, end_other = event_vars[other_id]
                        solver.add(start_var > end_other)
                        checked += 1
            before_ids = (
                event.metadata.get("before")
                if isinstance(event.metadata, dict)
                else None
            )
            if isinstance(before_ids, list):
                for other_id in before_ids:
                    if isinstance(other_id, str) and other_id in event_vars:
                        start_other, _ = event_vars[other_id]
                        solver.add(start_var < start_other)
                        checked += 1

        # 添加时序约束
        for entity in set(e for event in events for e in event.entities):
            entity_events = [e for e in events if entity in e.entities]
            sorted_events = sorted(entity_events, key=lambda e: e.timestamp)
            checked += 1

            for i in range(len(sorted_events) - 1):
                current = sorted_events[i]
                next_event = sorted_events[i + 1]

                if current.event_id in event_vars and next_event.event_id in event_vars:
                    _, end_curr = event_vars[current.event_id]
                    start_next, _ = event_vars[next_event.event_id]

                    # 添加约束：current.end <= next.start
                    solver.add(end_curr <= start_next)

        # 检查可满足性
        if solver.check() == z3.unsat:
            violations.append(
                ConstraintViolation(
                    constraint_type=ConstraintType.TIMELINE,
                    message="Z3 形式化验证：事件时间线约束不可满足",
                    evidence=["存在逻辑矛盾，请检查事件时间"],
                    severity="error",
                )
            )

        return violations, checked


def create_military_validator(
    audit_callback: AuditCallback | None = None,
) -> Z3EventTimelineValidator:
    """创建军事领域的事件时间线校验器（使用预定义规则）。"""
    return Z3EventTimelineValidator(
        causality_rules=DEFAULT_CAUSALITY_RULES,
        mutex_states=DEFAULT_MUTEX_STATES,
        audit_callback=audit_callback,
    )


def create_z3_audit_callback(
    task_id: str | None = None,
    trace_id_prefix: str = "z3_",
) -> tuple[AuditCallback, list[dict[str, object]]]:
    """创建 Z3 校验审计回调和结果收集器。"""
    traces: list[dict[str, object]] = []

    def callback(
        report: ValidationReport,
        events: list[TimelineEvent],
        duration_ms: int,
    ) -> None:
        import uuid

        entities: set[str] = set()
        for event in events:
            entities.update(event.entities)

        violation_records = [
            {
                "constraint_type": v.constraint_type.value,
                "message": v.message,
                "evidence": v.evidence,
                "severity": v.severity,
            }
            for v in report.violations
        ]

        trace: dict[str, object] = {
            "trace_id": f"{trace_id_prefix}{uuid.uuid4().hex[:12]}",
            "task_id": task_id,
            "duration_ms": duration_ms,
            "result": report.result.value,
            "checked_constraints": report.checked_constraints,
            "passed_constraints": report.passed_constraints,
            "violations": violation_records,
            "event_count": len(events),
            "entity_count": len(entities),
        }
        traces.append(trace)

    return callback, traces
