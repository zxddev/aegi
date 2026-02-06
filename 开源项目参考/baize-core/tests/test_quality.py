"""数据质量测试。"""

from __future__ import annotations

from baize_core.quality.expectations import (
    ExpectationValidator,
    QualityGate,
)


class TestExpectationValidator:
    """ExpectationValidator 测试。"""

    def test_empty_data(self) -> None:
        """测试空数据。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_not_null("col1")
        report = validator.validate([])
        assert report.is_success

    def test_not_null_pass(self) -> None:
        """测试非空检查通过。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_not_null("name")
        data = [{"name": "Alice"}, {"name": "Bob"}]
        report = validator.validate(data)
        assert report.is_success
        assert report.passed_expectations == 1

    def test_not_null_fail(self) -> None:
        """测试非空检查失败。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_not_null("name")
        data = [{"name": "Alice"}, {"name": None}]
        report = validator.validate(data)
        assert not report.is_success
        assert report.failed_expectations == 1

    def test_unique_pass(self) -> None:
        """测试唯一性检查通过。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_unique("id")
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        report = validator.validate(data)
        assert report.is_success

    def test_unique_fail(self) -> None:
        """测试唯一性检查失败。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_unique("id")
        data = [{"id": 1}, {"id": 1}, {"id": 2}]
        report = validator.validate(data)
        assert not report.is_success

    def test_in_set_pass(self) -> None:
        """测试值集合检查通过。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_values_in_set("status", ["active", "inactive"])
        data = [{"status": "active"}, {"status": "inactive"}]
        report = validator.validate(data)
        assert report.is_success

    def test_in_set_fail(self) -> None:
        """测试值集合检查失败。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_values_in_set("status", ["active", "inactive"])
        data = [{"status": "active"}, {"status": "unknown"}]
        report = validator.validate(data)
        assert not report.is_success

    def test_regex_pass(self) -> None:
        """测试正则检查通过。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_values_to_match_regex("email", r".*@.*\..*")
        data = [{"email": "test@example.com"}]
        report = validator.validate(data)
        assert report.is_success

    def test_between_pass(self) -> None:
        """测试范围检查通过。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_values_between("age", 0, 150)
        data = [{"age": 25}, {"age": 30}]
        report = validator.validate(data)
        assert report.is_success

    def test_between_fail(self) -> None:
        """测试范围检查失败。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_values_between("age", 0, 150)
        data = [{"age": 25}, {"age": -5}]
        report = validator.validate(data)
        assert not report.is_success

    def test_multiple_expectations(self) -> None:
        """测试多个期望。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_not_null("id")
        validator.expect_column_unique("id")
        validator.expect_column_values_between("score", 0, 100)
        data = [
            {"id": 1, "score": 80},
            {"id": 2, "score": 90},
        ]
        report = validator.validate(data)
        assert report.is_success
        assert report.total_expectations == 3
        assert report.passed_expectations == 3


class TestQualityGate:
    """QualityGate 测试。"""

    def test_gate_pass(self) -> None:
        """测试闸门通过。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_not_null("name")
        gate = QualityGate(validator, min_success_percent=100.0)
        data = [{"name": "Alice"}]
        passed, report = gate.check(data)
        assert passed

    def test_gate_fail(self) -> None:
        """测试闸门失败。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_not_null("name")
        gate = QualityGate(validator, min_success_percent=100.0)
        data = [{"name": None}]
        passed, report = gate.check(data)
        assert not passed

    def test_gate_partial_pass(self) -> None:
        """测试部分通过闸门。"""
        validator = ExpectationValidator("test_dataset")
        validator.expect_column_not_null("name")
        validator.expect_column_unique("name")
        gate = QualityGate(validator, min_success_percent=50.0)
        data = [{"name": "Alice"}, {"name": "Alice"}]  # not_null 通过, unique 失败
        passed, report = gate.check(data)
        assert passed  # 50% >= 50%
