"""约束校验测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from baize_core.validation.constraints import (
    CompositeValidator,
    ConstraintType,
    MutexValidator,
    TimelineEvent,
    TimelineValidator,
    Z3ConstraintValidator,
)


class TestTimelineValidator:
    """TimelineValidator 测试。"""

    def test_empty_events(self) -> None:
        """测试空事件列表。"""
        validator = TimelineValidator()
        report = validator.validate([])
        assert report.is_valid

    def test_single_event(self) -> None:
        """测试单个事件。"""
        events = [
            TimelineEvent(
                event_id="e1",
                timestamp=datetime.now(UTC),
                description="事件1",
                entities=["entity_a"],
            )
        ]
        validator = TimelineValidator()
        report = validator.validate(events)
        assert report.is_valid

    def test_multiple_entities(self) -> None:
        """测试多个实体的事件。"""
        events = [
            TimelineEvent(
                event_id="e1",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                description="事件1",
                entities=["entity_a"],
            ),
            TimelineEvent(
                event_id="e2",
                timestamp=datetime(2024, 1, 2, tzinfo=UTC),
                description="事件2",
                entities=["entity_a", "entity_b"],
            ),
        ]
        validator = TimelineValidator()
        report = validator.validate(events)
        assert report.checked_constraints >= 1


class TestMutexValidator:
    """MutexValidator 测试。"""

    def test_no_violation(self) -> None:
        """测试无违反。"""
        rules = [("state_a", "state_b")]
        validator = MutexValidator(rules)
        states = {"state_a": True, "state_b": False}
        report = validator.validate(states)
        assert report.is_valid

    def test_violation(self) -> None:
        """测试违反。"""
        rules = [("state_a", "state_b")]
        validator = MutexValidator(rules)
        states = {"state_a": True, "state_b": True}
        report = validator.validate(states)
        assert not report.is_valid
        assert len(report.violations) == 1
        assert report.violations[0].constraint_type == ConstraintType.MUTEX

    def test_multiple_rules(self) -> None:
        """测试多条规则。"""
        rules = [("a", "b"), ("c", "d")]
        validator = MutexValidator(rules)
        states = {"a": True, "b": True, "c": False, "d": False}
        report = validator.validate(states)
        assert len(report.violations) == 1


class TestZ3ConstraintValidator:
    """Z3ConstraintValidator 测试。"""

    def test_simplified_validate(self) -> None:
        """测试简化校验（Z3 可能不可用）。"""
        validator = Z3ConstraintValidator()
        constraints = [
            {
                "type": "range",
                "variables": {"x": "int"},
                "expression": "x >= 0",
            }
        ]
        report = validator.validate(constraints)
        # 根据 Z3 是否安装，结果可能不同
        assert report.checked_constraints == 1


class TestCompositeValidator:
    """CompositeValidator 测试。"""

    def test_add_validator(self) -> None:
        """测试添加校验器。"""
        composite = CompositeValidator()
        timeline_validator = TimelineValidator()
        composite.add_validator("timeline", timeline_validator)
        assert len(composite._validators) == 1

    def test_validate_all(self) -> None:
        """测试执行所有校验。"""
        composite = CompositeValidator()
        composite.add_validator("mutex", MutexValidator([("a", "b")]))
        data = {
            "mutex": {"a": False, "b": False},
        }
        reports = composite.validate_all(data)
        assert "mutex" in reports
        assert reports["mutex"].is_valid

    def test_get_summary(self) -> None:
        """测试获取摘要。"""
        composite = CompositeValidator()
        composite.add_validator("mutex", MutexValidator([("a", "b")]))
        data = {"mutex": {"a": True, "b": True}}
        reports = composite.validate_all(data)
        summary = composite.get_summary(reports)
        assert not summary["all_valid"]
        assert summary["total_violations"] == 1
