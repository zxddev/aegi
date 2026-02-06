"""约束校验器。"""

from __future__ import annotations

from typing import Any

from baize_core.validation.constraints_types import (
    ConstraintType,
    ConstraintValidator,
    ConstraintViolation,
    TimelineEvent,
    ValidationReport,
    ValidationResult,
)


class TimelineValidator(ConstraintValidator):
    """时间线一致性校验器。

    检查事件时间线是否存在逻辑矛盾。
    """

    def validate(self, events: list[TimelineEvent]) -> ValidationReport:
        """校验时间线一致性。"""
        violations: list[ConstraintViolation] = []
        checked = 0

        # 按实体分组事件
        entity_events: dict[str, list[TimelineEvent]] = {}
        for event in events:
            for entity in event.entities:
                if entity not in entity_events:
                    entity_events[entity] = []
                entity_events[entity].append(event)

        # 检查每个实体的时间线
        for entity, entity_event_list in entity_events.items():
            # 按时间排序
            sorted_events = sorted(entity_event_list, key=lambda e: e.timestamp)
            checked += 1

            # 检查是否有时间顺序问题
            for i in range(len(sorted_events) - 1):
                current = sorted_events[i]
                next_event = sorted_events[i + 1]

                # 检查因果关系（简化版本）
                if self._check_causality_violation(current, next_event):
                    violations.append(
                        ConstraintViolation(
                            constraint_type=ConstraintType.TIMELINE,
                            message=f"实体 '{entity}' 的事件时间顺序可能存在问题",
                            evidence=[
                                f"事件1: {current.description} ({current.timestamp})",
                                f"事件2: {next_event.description} ({next_event.timestamp})",
                            ],
                            severity="warning",
                        )
                    )

        result = ValidationResult.VALID if not violations else ValidationResult.INVALID
        return ValidationReport(
            result=result,
            violations=violations,
            checked_constraints=checked,
            passed_constraints=checked - len(violations),
        )

    def _check_causality_violation(
        self, event1: TimelineEvent, event2: TimelineEvent
    ) -> bool:
        """检查因果关系违反（简化实现）。"""
        # 这里可以添加更复杂的因果关系检查逻辑
        # 例如：检查事件描述中的因果关键词
        return False


class MutexValidator(ConstraintValidator):
    """互斥约束校验器。

    检查资源/状态是否存在互斥违反。
    """

    def __init__(self, mutex_rules: list[tuple[str, str]]) -> None:
        """初始化互斥校验器。

        Args:
            mutex_rules: 互斥规则列表，每项为 (状态A, 状态B) 表示 A 和 B 不能同时为真
        """
        self._rules = mutex_rules

    def validate(self, states: dict[str, bool]) -> ValidationReport:
        """校验互斥约束。"""
        violations: list[ConstraintViolation] = []
        checked = 0

        for state_a, state_b in self._rules:
            checked += 1
            if states.get(state_a, False) and states.get(state_b, False):
                violations.append(
                    ConstraintViolation(
                        constraint_type=ConstraintType.MUTEX,
                        message=f"互斥违反: '{state_a}' 和 '{state_b}' 不能同时为真",
                        evidence=[f"{state_a}=True", f"{state_b}=True"],
                        severity="error",
                    )
                )

        result = ValidationResult.VALID if not violations else ValidationResult.INVALID
        return ValidationReport(
            result=result,
            violations=violations,
            checked_constraints=checked,
            passed_constraints=checked - len(violations),
        )


class CompositeValidator:
    """组合校验器。"""

    def __init__(self) -> None:
        """初始化组合校验器。"""
        self._validators: list[tuple[str, ConstraintValidator]] = []

    def add_validator(self, name: str, validator: ConstraintValidator) -> None:
        """添加校验器。"""
        self._validators.append((name, validator))

    def validate_all(self, data_map: dict[str, Any]) -> dict[str, ValidationReport]:
        """执行所有校验。"""
        results: dict[str, ValidationReport] = {}
        for name, validator in self._validators:
            if name in data_map:
                results[name] = validator.validate(data_map[name])
        return results

    def get_summary(self, reports: dict[str, ValidationReport]) -> dict[str, Any]:
        """获取校验摘要。"""
        total_checked = sum(r.checked_constraints for r in reports.values())
        total_passed = sum(r.passed_constraints for r in reports.values())
        total_violations = sum(len(r.violations) for r in reports.values())
        all_valid = all(r.is_valid for r in reports.values())
        return {
            "all_valid": all_valid,
            "total_checked": total_checked,
            "total_passed": total_passed,
            "total_violations": total_violations,
            "validators": {
                name: {
                    "result": report.result.value,
                    "violations": len(report.violations),
                }
                for name, report in reports.items()
            },
        }
