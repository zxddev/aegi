"""评测套件模块。

提供评测数据集、执行器、指标计算和报告生成功能。
"""

from baize_core.evaluation.datasets.schema import (
    CaseResult,
    EvaluationCase,
    EvaluationTaskType,
    ExpectedEntity,
    ExpectedEvent,
    ExpectedLocation,
    SuiteResult,
)
from baize_core.evaluation.metrics import (
    ExtractedData,
    MetricsCalculator,
    MetricsResult,
    compute_metrics_for_case,
)
from baize_core.evaluation.report import (
    ReportGenerator,
    generate_evaluation_report,
)
from baize_core.evaluation.runner import (
    EvaluationRunner,
    get_available_suites,
    get_suite_info,
)

__all__ = [
    # Schema
    "CaseResult",
    "EvaluationCase",
    "EvaluationTaskType",
    "ExpectedEntity",
    "ExpectedEvent",
    "ExpectedLocation",
    "SuiteResult",
    # Metrics
    "ExtractedData",
    "MetricsCalculator",
    "MetricsResult",
    "compute_metrics_for_case",
    # Report
    "ReportGenerator",
    "generate_evaluation_report",
    # Runner
    "EvaluationRunner",
    "get_available_suites",
    "get_suite_info",
]
