"""评测套件测试。

测试覆盖：
1. 评测用例 Schema 验证
2. 指标计算单元测试
3. 报告生成测试
4. 执行器基本功能测试
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from baize_core.evaluation.datasets.schema import (
    CaseResult,
    EvaluationCase,
    EvaluationTaskType,
    ExpectedEntity,
    ExpectedEvent,
    ExpectedLocation,
    SuiteResult,
    load_suite_cases,
)
from baize_core.evaluation.metrics import (
    MetricsCalculator,
    MetricsResult,
)
from baize_core.evaluation.report import ReportGenerator
from baize_core.evaluation.runner import (
    EvaluationRunner,
    get_available_suites,
    get_suite_info,
)


class TestEvaluationCaseSchema:
    """评测用例 Schema 测试。"""

    def test_minimal_case(self) -> None:
        """测试最小必填字段。"""
        case = EvaluationCase(
            case_id="test_001",
            name="测试用例",
            task_type=EvaluationTaskType.STRATEGIC_SITUATION,
            query="测试问题",
        )
        assert case.case_id == "test_001"
        assert case.task_type == EvaluationTaskType.STRATEGIC_SITUATION
        assert case.min_sources == 5
        assert case.timeout_minutes == 30

    def test_full_case(self) -> None:
        """测试完整字段。"""
        case = EvaluationCase(
            case_id="test_002",
            name="完整测试用例",
            description="描述",
            task_type=EvaluationTaskType.OPERATIONAL_ACTION,
            query="研究问题",
            expected_entities=[
                ExpectedEntity(name="实体A", entity_type="Unit"),
            ],
            expected_events=[
                ExpectedEvent(event_type="Deployment", description="部署事件"),
            ],
            expected_locations=[
                ExpectedLocation(name="地点A", latitude=30.0, longitude=120.0),
            ],
            min_sources=10,
            timeout_minutes=60,
            tags=["标签1", "标签2"],
            difficulty="hard",
        )
        assert len(case.expected_entities) == 1
        assert len(case.expected_events) == 1
        assert len(case.expected_locations) == 1
        assert case.min_sources == 10
        assert case.difficulty == "hard"

    def test_case_yaml_roundtrip(self) -> None:
        """测试 YAML 序列化/反序列化。"""
        case = EvaluationCase(
            case_id="yaml_test",
            name="YAML测试",
            task_type=EvaluationTaskType.STRATEGIC_SITUATION,
            query="测试问题",
            expected_entities=[
                ExpectedEntity(name="测试实体", entity_type="Actor"),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "test.yaml"
            case.to_yaml(yaml_path)
            loaded = EvaluationCase.from_yaml(yaml_path)

        assert loaded.case_id == case.case_id
        assert loaded.name == case.name
        assert len(loaded.expected_entities) == 1
        assert loaded.expected_entities[0].name == "测试实体"

    def test_case_result_schema(self) -> None:
        """测试用例结果 Schema。"""
        result = CaseResult(
            case_id="test_001",
            success=True,
            elapsed_seconds=10.5,
            evidence_count=5,
            source_count=3,
        )
        assert result.success
        assert result.elapsed_seconds == 10.5
        assert result.evidence_count == 5

    def test_suite_result_schema(self) -> None:
        """测试套件结果 Schema。"""
        case_results = [
            CaseResult(case_id="c1", success=True, elapsed_seconds=10.0),
            CaseResult(case_id="c2", success=False, error_message="失败"),
        ]
        result = SuiteResult(
            suite_name="test",
            total_cases=2,
            completed_cases=2,
            failed_cases=1,
            pass_rate=0.5,
            case_results=case_results,
        )
        assert result.total_cases == 2
        assert result.failed_cases == 1
        assert result.pass_rate == 0.5


class TestMetricsCalculator:
    """指标计算测试。"""

    def test_entity_extraction_f1_perfect(self) -> None:
        """测试实体抽取 F1 - 完美匹配。"""
        calc = MetricsCalculator()
        expected = [
            ExpectedEntity(name="实体A", entity_type="Unit"),
            ExpectedEntity(name="实体B", entity_type="Actor"),
        ]
        extracted_names = ["实体A", "实体B"]
        extracted_types = {"实体A": "Unit", "实体B": "Actor"}

        result = calc.entity_extraction_f1(expected, extracted_names, extracted_types)

        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0

    def test_entity_extraction_f1_partial(self) -> None:
        """测试实体抽取 F1 - 部分匹配。"""
        calc = MetricsCalculator()
        expected = [
            ExpectedEntity(name="实体A", entity_type="Unit"),
            ExpectedEntity(name="实体B", entity_type="Actor"),
        ]
        extracted_names = ["实体A", "实体C"]  # 只匹配一个

        result = calc.entity_extraction_f1(expected, extracted_names, {})

        assert result["recall"] == 0.5  # 2个预期，只匹配1个
        assert result["precision"] == 0.5  # 2个抽取，只有1个正确

    def test_entity_extraction_f1_with_aliases(self) -> None:
        """测试实体抽取 F1 - 别名匹配。"""
        calc = MetricsCalculator()
        expected = [
            ExpectedEntity(
                name="南海舰队", entity_type="Unit", aliases=["南部战区海军"]
            ),
        ]
        extracted_names = ["南部战区海军"]  # 通过别名匹配

        result = calc.entity_extraction_f1(expected, extracted_names, {})

        assert result["recall"] == 1.0
        assert result["f1"] == 1.0

    def test_entity_extraction_f1_empty(self) -> None:
        """测试实体抽取 F1 - 空输入。"""
        calc = MetricsCalculator()
        result = calc.entity_extraction_f1([], [], {})
        assert result["f1"] == 1.0  # 无预期时默认满分

    def test_event_extraction_f1(self) -> None:
        """测试事件抽取 F1。"""
        calc = MetricsCalculator()
        expected = [
            ExpectedEvent(event_type="Deployment", description="部署"),
            ExpectedEvent(event_type="Exercise", description="演习"),
        ]
        extracted_types = ["Deployment", "Movement"]

        result = calc.event_extraction_f1(expected, extracted_types, [])

        assert result["recall"] == 0.5  # 2个预期，匹配1个
        assert result["precision"] == 0.5  # 2个抽取，正确1个

    def test_geolocation_match_rate_by_name(self) -> None:
        """测试地理位置匹配 - 名称匹配。"""
        calc = MetricsCalculator()
        expected = [
            ExpectedLocation(name="南海", latitude=15.0, longitude=115.0),
        ]
        extracted = [("南海", None, None)]

        rate = calc.geolocation_match_rate(expected, extracted)
        assert rate == 1.0

    def test_geolocation_match_rate_by_coords(self) -> None:
        """测试地理位置匹配 - 坐标匹配。"""
        calc = MetricsCalculator()
        expected = [
            ExpectedLocation(
                name="某地", latitude=30.0, longitude=120.0, tolerance_km=100
            ),
        ]
        # 在容差范围内的坐标
        extracted = [("其他名称", 30.5, 120.5)]

        rate = calc.geolocation_match_rate(expected, extracted)
        assert rate == 1.0  # 坐标在100km容差内

    def test_source_diversity(self) -> None:
        """测试来源多样性。"""
        # 创建模拟的 Evidence 对象
        from dataclasses import dataclass

        @dataclass
        class MockEvidence:
            evidence_uid: str
            uri: str | None
            source: str | None
            conflict_types: list[str] | None = None

        calc = MetricsCalculator()
        evidence = [
            MockEvidence("e1", "https://example.com/a", "example.com"),
            MockEvidence("e2", "https://example.com/b", "example.com"),
            MockEvidence("e3", "https://other.org/c", "other.org"),
        ]

        diversity = calc.source_diversity(evidence)  # type: ignore
        assert diversity == 2  # 2个不同域名

    def test_metrics_result_to_dict(self) -> None:
        """测试指标结果转字典。"""
        result = MetricsResult(
            entity_f1=0.8,
            citation_hit_rate=0.9,
            crawl_success_rate=0.95,
        )
        data = result.to_dict()

        assert "extraction" in data
        assert "evidence" in data
        assert "operations" in data
        assert data["extraction"]["entity_f1"] == 0.8
        assert data["evidence"]["citation_hit_rate"] == 0.9


class TestReportGenerator:
    """报告生成测试。"""

    def test_generate_markdown(self) -> None:
        """测试 Markdown 报告生成。"""
        result = SuiteResult(
            suite_name="test",
            total_cases=3,
            completed_cases=3,
            failed_cases=1,
            pass_rate=0.67,
            avg_elapsed_seconds=15.5,
            case_results=[
                CaseResult(case_id="c1", success=True, elapsed_seconds=10.0),
                CaseResult(case_id="c2", success=True, elapsed_seconds=12.0),
                CaseResult(case_id="c3", success=False, error_message="超时"),
            ],
        )

        generator = ReportGenerator()
        md = generator.generate_markdown(result)

        assert "# 评测报告：test" in md
        assert "总用例数**: 3" in md
        assert "通过率**: 67" in md
        assert "c1" in md
        assert "c3" in md
        assert "超时" in md

    def test_generate_html(self) -> None:
        """测试 HTML 报告生成。"""
        result = SuiteResult(
            suite_name="test",
            total_cases=2,
            completed_cases=2,
            failed_cases=0,
            pass_rate=1.0,
            case_results=[
                CaseResult(case_id="c1", success=True, elapsed_seconds=10.0),
            ],
        )

        generator = ReportGenerator()
        html = generator.generate_html(result)

        assert "<!DOCTYPE html>" in html
        assert "评测报告" in html
        assert "test" in html
        assert "c1" in html

    def test_save_reports(self) -> None:
        """测试报告保存。"""
        result = SuiteResult(
            suite_name="save_test",
            total_cases=1,
            completed_cases=1,
            failed_cases=0,
            pass_rate=1.0,
            case_results=[
                CaseResult(case_id="c1", success=True),
            ],
        )

        generator = ReportGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "report.html"
            md_path = Path(tmpdir) / "report.md"

            generator.save_html(result, html_path)
            generator.save_markdown(result, md_path)

            assert html_path.exists()
            assert md_path.exists()
            assert "save_test" in html_path.read_text(encoding="utf-8")
            assert "save_test" in md_path.read_text(encoding="utf-8")


class TestEvaluationRunner:
    """评测执行器测试。"""

    def test_get_available_suites(self) -> None:
        """测试获取可用套件。"""
        suites = get_available_suites()
        # 应该包含我们创建的套件
        assert "strategic" in suites
        assert "operational" in suites

    def test_get_suite_info(self) -> None:
        """测试获取套件信息。"""
        info = get_suite_info("strategic")
        assert info["name"] == "strategic"
        assert info["case_count"] >= 5  # 我们创建了5个用例
        assert len(info["cases"]) >= 5

    def test_load_suite_cases(self) -> None:
        """测试加载套件用例。"""
        from baize_core.evaluation.runner import DATASETS_DIR

        cases = load_suite_cases(DATASETS_DIR / "strategic")
        assert len(cases) >= 5

        # 验证用例内容
        case_ids = {c.case_id for c in cases}
        assert "strategic_001" in case_ids

    @pytest.mark.asyncio
    async def test_runner_dry_run(self) -> None:
        """测试执行器 dry-run 模式。"""
        runner = EvaluationRunner(context=None)
        result = await runner.run_suite("strategic", parallel=2, dry_run=True)

        assert result.suite_name == "strategic"
        assert result.total_cases >= 5
        assert result.completed_cases == result.total_cases
        assert result.failed_cases == 0
        assert result.pass_rate == 1.0

    @pytest.mark.asyncio
    async def test_runner_checkpoint(self) -> None:
        """测试检查点功能。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir)
            runner = EvaluationRunner(
                context=None,
                checkpoint_dir=checkpoint_dir,
            )

            await runner.run_suite("strategic", dry_run=True)

            # 检查检查点文件是否创建
            checkpoint_path = checkpoint_dir / "strategic_checkpoint.json"
            assert checkpoint_path.exists()


class TestIntegration:
    """集成测试。"""

    @pytest.mark.asyncio
    async def test_full_evaluation_pipeline(self) -> None:
        """测试完整评测流程。"""
        from baize_core.evaluation.report import generate_evaluation_report

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # 执行评测
            runner = EvaluationRunner(
                context=None,
                checkpoint_dir=output_dir / "checkpoints",
            )
            result = await runner.run_suite("operational", dry_run=True)

            # 生成报告
            report_paths = generate_evaluation_report(result, output_dir)

            # 验证结果
            assert result.total_cases >= 5
            assert "html" in report_paths
            assert "md" in report_paths
            assert report_paths["html"].exists()
            assert report_paths["md"].exists()
