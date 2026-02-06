"""评测用例 Schema 定义。

定义评测用例的结构，支持战略态势和行动研究两类任务。
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class EvaluationTaskType(str, Enum):
    """评测任务类型。"""

    STRATEGIC_SITUATION = "strategic_situation"
    """战略态势。"""

    OPERATIONAL_ACTION = "operational_action"
    """行动研究。"""


class ExpectedEntity(BaseModel):
    """预期实体。

    用于评估实体抽取质量。
    """

    name: str = Field(min_length=1, description="实体名称")
    entity_type: str = Field(min_length=1, description="实体类型")
    aliases: list[str] = Field(default_factory=list, description="别名（用于模糊匹配）")
    required: bool = Field(default=True, description="是否必须抽取到")


class ExpectedEvent(BaseModel):
    """预期事件。

    用于评估事件抽取质量。
    """

    event_type: str = Field(min_length=1, description="事件类型")
    description: str = Field(min_length=1, description="事件描述")
    participants: list[str] = Field(default_factory=list, description="参与方")
    required: bool = Field(default=True, description="是否必须抽取到")


class ExpectedLocation(BaseModel):
    """预期地理位置。

    用于评估地理定位质量。
    """

    name: str = Field(min_length=1, description="地点名称")
    country: str | None = Field(default=None, description="国家")
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0, description="纬度")
    longitude: float | None = Field(
        default=None, ge=-180.0, le=180.0, description="经度"
    )
    tolerance_km: float = Field(default=50.0, ge=0.0, description="坐标容差（公里）")


class ExpectedSource(BaseModel):
    """预期来源。

    用于评估来源覆盖。
    """

    domain: str = Field(min_length=1, description="域名或来源标识")
    required: bool = Field(default=False, description="是否必须命中")


class EvaluationCase(BaseModel):
    """评测用例。

    定义单个评测用例的完整结构。
    """

    case_id: str = Field(min_length=1, description="用例 ID")
    name: str = Field(min_length=1, description="用例名称")
    description: str = Field(default="", description="用例描述")
    task_type: EvaluationTaskType = Field(description="任务类型")
    query: str = Field(min_length=1, description="研究问题/目标")

    # 预期输出（用于评估抽取质量）
    expected_entities: list[ExpectedEntity] = Field(
        default_factory=list, description="预期实体"
    )
    expected_events: list[ExpectedEvent] = Field(
        default_factory=list, description="预期事件"
    )
    expected_locations: list[ExpectedLocation] = Field(
        default_factory=list, description="预期地理位置"
    )
    expected_sources: list[ExpectedSource] = Field(
        default_factory=list, description="预期来源"
    )

    # 质量阈值
    min_sources: int = Field(default=5, ge=1, description="最少来源数")
    min_citations: int = Field(default=3, ge=0, description="最少引用数")
    max_conflict_rate: float = Field(
        default=0.3, ge=0.0, le=1.0, description="最大冲突率"
    )

    # 执行配置
    timeout_minutes: int = Field(
        default=30, ge=1, le=120, description="超时时间（分钟）"
    )
    constraints: list[str] = Field(default_factory=list, description="任务约束")
    time_window: str | None = Field(default=None, description="时间窗口")
    region: str | None = Field(default=None, description="区域限制")

    # 元数据
    tags: list[str] = Field(default_factory=list, description="标签")
    difficulty: str = Field(default="medium", description="难度级别")
    notes: str = Field(default="", description="备注")

    @classmethod
    def from_yaml(cls, path: Path) -> EvaluationCase:
        """从 YAML 文件加载评测用例。

        Args:
            path: YAML 文件路径

        Returns:
            EvaluationCase 实例
        """
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    def to_yaml(self, path: Path) -> None:
        """保存评测用例到 YAML 文件。

        Args:
            path: 目标文件路径
        """
        data = self.model_dump(mode="json", exclude_none=True, exclude_defaults=False)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data, f, allow_unicode=True, default_flow_style=False, sort_keys=False
            )


class CaseResult(BaseModel):
    """单个用例的评测结果。"""

    case_id: str = Field(description="用例 ID")
    success: bool = Field(description="是否成功完成")
    error_message: str | None = Field(default=None, description="错误信息")

    # 执行信息
    elapsed_seconds: float = Field(default=0.0, ge=0.0, description="执行耗时（秒）")
    report_uid: str | None = Field(default=None, description="生成的报告 UID")

    # 指标结果（由 metrics 模块计算后填充）
    metrics: dict[str, Any] = Field(default_factory=dict, description="指标结果")

    # 原始数据引用（用于详细分析）
    evidence_count: int = Field(default=0, ge=0, description="证据数量")
    source_count: int = Field(default=0, ge=0, description="来源数量")
    entity_count: int = Field(default=0, ge=0, description="抽取实体数")
    event_count: int = Field(default=0, ge=0, description="抽取事件数")


class SuiteResult(BaseModel):
    """评测套件结果。"""

    suite_name: str = Field(description="套件名称")
    total_cases: int = Field(ge=0, description="总用例数")
    completed_cases: int = Field(ge=0, description="完成用例数")
    failed_cases: int = Field(ge=0, description="失败用例数")

    # 汇总指标
    pass_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="通过率")
    avg_elapsed_seconds: float = Field(default=0.0, ge=0.0, description="平均耗时")
    aggregated_metrics: dict[str, float] = Field(
        default_factory=dict, description="汇总指标"
    )

    # 逐用例结果
    case_results: list[CaseResult] = Field(default_factory=list, description="用例结果")

    # 执行元数据
    started_at: str | None = Field(default=None, description="开始时间")
    finished_at: str | None = Field(default=None, description="结束时间")
    checkpoint_path: str | None = Field(default=None, description="检查点路径")


def load_suite_cases(suite_dir: Path) -> list[EvaluationCase]:
    """加载评测套件中的所有用例。

    Args:
        suite_dir: 套件目录（包含 YAML 文件）

    Returns:
        用例列表
    """
    cases: list[EvaluationCase] = []
    if not suite_dir.exists():
        return cases

    for yaml_path in sorted(suite_dir.glob("*.yaml")):
        try:
            case = EvaluationCase.from_yaml(yaml_path)
            cases.append(case)
        except Exception as e:
            # 记录但不中断
            print(f"警告: 加载用例 {yaml_path} 失败: {e}")

    return cases
