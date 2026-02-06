"""评测执行器。

支持评测用例的加载、并行执行和中断恢复。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from baize_core.evaluation.datasets.schema import (
    CaseResult,
    EvaluationCase,
    EvaluationTaskType,
    SuiteResult,
    load_suite_cases,
)
from baize_core.schemas.policy import SensitivityLevel
from baize_core.schemas.storm import StormTaskType
from baize_core.schemas.task import TaskSpec

if TYPE_CHECKING:
    from baize_core.orchestration.storm_graph import StormContext


# 数据集目录
DATASETS_DIR = Path(__file__).parent / "datasets"


class EvaluationRunner:
    """评测执行器。

    职责：
    1. 加载评测用例
    2. 并行执行评测
    3. 支持中断恢复
    4. 收集评测结果
    """

    def __init__(
        self,
        *,
        context: StormContext | None = None,
        checkpoint_dir: Path | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> None:
        """初始化评测执行器。

        Args:
            context: STORM 运行上下文（用于执行研究任务）
            checkpoint_dir: 检查点目录
            progress_callback: 进度回调函数 (case_id, completed, total)
        """
        self._context = context
        self._checkpoint_dir = checkpoint_dir or Path("./eval_checkpoints")
        self._progress_callback = progress_callback

    async def run_suite(
        self,
        suite_name: str,
        *,
        parallel: int = 1,
        dry_run: bool = False,
    ) -> SuiteResult:
        """运行评测套件。

        Args:
            suite_name: 套件名称 (strategic/operational)
            parallel: 并行数
            dry_run: 是否仅验证用例（不实际执行）

        Returns:
            SuiteResult 评测结果
        """
        # 加载用例
        suite_dir = DATASETS_DIR / suite_name
        cases = load_suite_cases(suite_dir)
        if not cases:
            return SuiteResult(
                suite_name=suite_name,
                total_cases=0,
                completed_cases=0,
                failed_cases=0,
            )

        # 初始化结果
        result = SuiteResult(
            suite_name=suite_name,
            total_cases=len(cases),
            completed_cases=0,
            failed_cases=0,
            started_at=datetime.now(UTC).isoformat(),
        )

        # 检查是否有检查点可恢复
        checkpoint_path = self._checkpoint_dir / f"{suite_name}_checkpoint.json"
        completed_ids: set[str] = set()
        if checkpoint_path.exists():
            checkpoint_data = self._load_checkpoint(checkpoint_path)
            raw_results = checkpoint_data.get("case_results", [])
            result.case_results = [
                CaseResult.model_validate(item) for item in raw_results
            ]
            completed_ids = {r.case_id for r in result.case_results}
            result.completed_cases = len(completed_ids)

        # 过滤待执行的用例
        pending_cases = [c for c in cases if c.case_id not in completed_ids]

        if dry_run:
            # 仅验证用例，不实际执行
            for case in pending_cases:
                case_result = CaseResult(
                    case_id=case.case_id,
                    success=True,
                    elapsed_seconds=0.0,
                )
                result.case_results.append(case_result)
                result.completed_cases += 1
            # 保存检查点
            self._save_checkpoint(checkpoint_path, result)
        else:
            # 并行执行
            semaphore = asyncio.Semaphore(parallel)
            tasks = [
                self._run_case_with_semaphore(case, semaphore, result, checkpoint_path)
                for case in pending_cases
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        # 计算汇总指标
        result.finished_at = datetime.now(UTC).isoformat()
        result.failed_cases = sum(1 for r in result.case_results if not r.success)
        result.pass_rate = (
            (result.completed_cases - result.failed_cases) / result.total_cases
            if result.total_cases > 0
            else 0.0
        )
        elapsed_list = [r.elapsed_seconds for r in result.case_results if r.success]
        result.avg_elapsed_seconds = (
            sum(elapsed_list) / len(elapsed_list) if elapsed_list else 0.0
        )
        result.checkpoint_path = str(checkpoint_path)

        # 聚合指标
        result.aggregated_metrics = self._aggregate_metrics(result.case_results)

        return result

    async def _run_case_with_semaphore(
        self,
        case: EvaluationCase,
        semaphore: asyncio.Semaphore,
        result: SuiteResult,
        checkpoint_path: Path,
    ) -> None:
        """带信号量控制的用例执行。

        Args:
            case: 评测用例
            semaphore: 并发信号量
            result: 结果对象（用于追加）
            checkpoint_path: 检查点路径
        """
        async with semaphore:
            case_result = await self.run_case(case)
            result.case_results.append(case_result)
            result.completed_cases += 1

            # 写入检查点
            self._save_checkpoint(checkpoint_path, result)

            # 进度回调
            if self._progress_callback:
                self._progress_callback(
                    case.case_id, result.completed_cases, result.total_cases
                )

    async def run_case(self, case: EvaluationCase) -> CaseResult:
        """执行单个评测用例。

        Args:
            case: 评测用例

        Returns:
            CaseResult 用例结果
        """
        start_time = time.time()

        try:
            # 转换任务类型
            storm_task_type = (
                StormTaskType.STRATEGIC_SITUATION
                if case.task_type == EvaluationTaskType.STRATEGIC_SITUATION
                else StormTaskType.OPERATIONAL_ACTION
            )

            # 如果有上下文，执行实际研究
            if self._context is not None:
                report_uid, metrics_data = await self._execute_storm_task(
                    case, storm_task_type
                )
            else:
                # 无上下文时，仅返回模拟结果
                report_uid = None
                metrics_data = {}

            elapsed = time.time() - start_time

            return CaseResult(
                case_id=case.case_id,
                success=True,
                elapsed_seconds=elapsed,
                report_uid=report_uid,
                metrics=metrics_data,
            )

        except TimeoutError:
            elapsed = time.time() - start_time
            return CaseResult(
                case_id=case.case_id,
                success=False,
                error_message=f"执行超时（{case.timeout_minutes} 分钟）",
                elapsed_seconds=elapsed,
            )
        except Exception as e:
            elapsed = time.time() - start_time
            return CaseResult(
                case_id=case.case_id,
                success=False,
                error_message=str(e),
                elapsed_seconds=elapsed,
            )

    async def _execute_storm_task(
        self,
        case: EvaluationCase,
        task_type: StormTaskType,
    ) -> tuple[str | None, dict[str, Any]]:
        """执行 STORM 研究任务。

        Args:
            case: 评测用例
            task_type: STORM 任务类型

        Returns:
            (report_uid, metrics_data) 元组
        """
        from baize_core.orchestration.storm_graph import build_storm_graph

        if self._context is None:
            return None, {}

        # 构建任务规范
        task = TaskSpec(
            task_id=f"eval_{case.case_id}_{int(time.time())}",
            objective=case.query,
            constraints=case.constraints,
            time_window=case.time_window,
            region=case.region,
            sensitivity=SensitivityLevel.INTERNAL,
        )

        # 构建并执行 STORM 图
        graph = cast(Any, build_storm_graph(self._context))
        initial_state = {
            "task": task,
            "task_type": task_type,
            "outline": None,
            "research": None,
            "report": None,
            "report_record": None,
            "evidence": [],
            "chunks": [],
            "artifacts": [],
            "review": None,
        }

        # 带超时执行
        timeout_seconds = case.timeout_minutes * 60
        result = await asyncio.wait_for(
            graph.ainvoke(initial_state),
            timeout=timeout_seconds,
        )

        # 提取结果
        report = result.get("report")
        report_uid = report.report_uid if report else None
        evidence_count = len(result.get("evidence", []))
        source_count = len({e.source for e in result.get("evidence", []) if e.source})

        metrics_data = {
            "evidence_count": evidence_count,
            "source_count": source_count,
        }

        return report_uid, metrics_data

    async def resume(self, checkpoint_path: Path) -> SuiteResult:
        """从检查点恢复执行。

        Args:
            checkpoint_path: 检查点文件路径

        Returns:
            SuiteResult 评测结果
        """
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"检查点文件不存在: {checkpoint_path}")

        checkpoint_data = self._load_checkpoint(checkpoint_path)
        suite_name = checkpoint_data.get("suite_name", "unknown")

        return await self.run_suite(suite_name)

    def _load_checkpoint(self, path: Path) -> dict[str, Any]:
        """加载检查点。

        Args:
            path: 检查点路径

        Returns:
            检查点数据
        """
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _save_checkpoint(self, path: Path, result: SuiteResult) -> None:
        """保存检查点。

        Args:
            path: 检查点路径
            result: 当前结果
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "suite_name": result.suite_name,
            "total_cases": result.total_cases,
            "completed_cases": result.completed_cases,
            "case_results": [r.model_dump() for r in result.case_results],
            "saved_at": datetime.now(UTC).isoformat(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _aggregate_metrics(
        self,
        case_results: list[CaseResult],
    ) -> dict[str, float]:
        """聚合所有用例的指标。

        Args:
            case_results: 用例结果列表

        Returns:
            聚合指标字典
        """
        aggregated: dict[str, list[float]] = {}

        for case_result in case_results:
            if not case_result.success:
                continue
            for key, value in case_result.metrics.items():
                if isinstance(value, (int, float)):
                    if key not in aggregated:
                        aggregated[key] = []
                    aggregated[key].append(float(value))

        # 计算平均值
        return {
            key: sum(values) / len(values) if values else 0.0
            for key, values in aggregated.items()
        }


def get_available_suites() -> list[str]:
    """获取可用的评测套件列表。

    Returns:
        套件名称列表
    """
    suites = []
    if DATASETS_DIR.exists():
        for item in DATASETS_DIR.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                # 检查是否有 YAML 文件
                yaml_files = list(item.glob("*.yaml"))
                if yaml_files:
                    suites.append(item.name)
    return sorted(suites)


def get_suite_info(suite_name: str) -> dict[str, Any]:
    """获取评测套件信息。

    Args:
        suite_name: 套件名称

    Returns:
        套件信息字典
    """
    suite_dir = DATASETS_DIR / suite_name
    cases = load_suite_cases(suite_dir)

    return {
        "name": suite_name,
        "case_count": len(cases),
        "cases": [
            {
                "case_id": c.case_id,
                "name": c.name,
                "difficulty": c.difficulty,
                "tags": c.tags,
            }
            for c in cases
        ],
    }
