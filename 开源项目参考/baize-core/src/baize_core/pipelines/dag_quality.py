"""质量检查 DAG - 数据质量闸门。

实现数据质量检查流水线：
1. 证据链完整性检查
2. 数据质量规则校验
3. 异常告警
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QualityConfig:
    """质量检查 DAG 配置。"""

    dag_id: str = "data_quality"
    schedule_interval: str = "0 6 * * *"  # 每天早 6 点
    start_date: datetime = field(default_factory=lambda: datetime(2024, 1, 1))
    catchup: bool = False
    max_active_runs: int = 1
    default_args: dict[str, Any] = field(default_factory=dict)

    # 检查配置
    check_last_hours: int = 24  # 检查最近 N 小时的数据

    # 告警配置
    alert_on_failure: bool = True
    alert_webhook: str = ""


def create_quality_dag(config: QualityConfig) -> Any:
    """创建质量检查 DAG。

    Args:
        config: DAG 配置

    Returns:
        Airflow DAG 对象
    """
    try:
        from airflow import DAG
        from airflow.operators.empty import EmptyOperator
        from airflow.operators.python import BranchPythonOperator, PythonOperator
    except ImportError:
        logger.warning("Airflow 未安装，返回模拟 DAG")
        return _create_mock_dag(config)

    default_args = {
        "owner": "baize-core",
        "depends_on_past": False,
        "email_on_failure": config.alert_on_failure,
        "email_on_retry": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
        **config.default_args,
    }

    dag = DAG(
        dag_id=config.dag_id,
        default_args=default_args,
        description="数据质量检查流水线",
        schedule_interval=config.schedule_interval,
        start_date=config.start_date,
        catchup=config.catchup,
        max_active_runs=config.max_active_runs,
        tags=["quality", "validation"],
    )

    with dag:
        # 任务 1: 加载待检查数据
        load_data = PythonOperator(
            task_id="load_data",
            python_callable=_load_recent_data,
            op_kwargs={"hours": config.check_last_hours},
        )

        # 任务 2: 证据链完整性检查
        check_evidence = PythonOperator(
            task_id="check_evidence_chain",
            python_callable=_check_evidence_chain,
        )

        # 任务 3: 数据质量规则校验
        check_quality = PythonOperator(
            task_id="check_quality_rules",
            python_callable=_check_quality_rules,
        )

        # 任务 4: 分支决策
        branch = BranchPythonOperator(
            task_id="branch_on_result",
            python_callable=_decide_branch,
        )

        # 任务 5a: 质量通过
        quality_passed = EmptyOperator(
            task_id="quality_passed",
        )

        # 任务 5b: 发送告警
        send_alert = PythonOperator(
            task_id="send_alert",
            python_callable=_send_alert,
            op_kwargs={"webhook": config.alert_webhook},
        )

        # 任务 6: 生成报告
        generate_report = PythonOperator(
            task_id="generate_report",
            python_callable=_generate_quality_report,
            trigger_rule="none_failed_min_one_success",
        )

        # 定义依赖
        load_data >> [check_evidence, check_quality] >> branch
        branch >> [quality_passed, send_alert] >> generate_report

    return dag


def _load_recent_data(hours: int, **context: Any) -> dict[str, Any]:
    """加载最近的数据。"""
    import asyncio

    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    async def _load() -> dict[str, Any]:
        from baize_core.config.settings import get_settings
        from baize_core.storage.postgres import PostgresStore

        settings = get_settings()
        store = PostgresStore.from_dsn(settings.database_url)
        await store.connect()

        # 加载最近的数据
        tasks = await store.get_tasks_since(cutoff)
        artifacts = await store.get_artifacts_since(cutoff)
        evidence = await store.get_evidence_since(cutoff)

        await store.close()

        return {
            "tasks": [t.task_id for t in tasks],
            "artifacts": [a.artifact_uid for a in artifacts],
            "evidence": [e.evidence_uid for e in evidence],
            "cutoff": cutoff.isoformat(),
        }

    data = asyncio.run(_load())
    context["ti"].xcom_push(key="recent_data", value=data)
    logger.info(
        "加载数据: %d 任务, %d Artifact, %d Evidence",
        len(data["tasks"]),
        len(data["artifacts"]),
        len(data["evidence"]),
    )
    return data


def _check_evidence_chain(**context: Any) -> dict[str, Any]:
    """证据链完整性检查。"""
    import asyncio

    data = context["ti"].xcom_pull(key="recent_data", task_ids="load_data") or {}

    async def _check() -> dict[str, Any]:
        from baize_core.config.settings import get_settings
        from baize_core.evidence.validator import EvidenceValidator
        from baize_core.storage.postgres import PostgresStore

        settings = get_settings()
        store = PostgresStore.from_dsn(settings.database_url)
        await store.connect()

        validator = EvidenceValidator()
        results: dict[str, Any] = {
            "checked": 0,
            "passed": 0,
            "failed": 0,
            "errors": [],
        }

        for task_id in data.get("tasks", []):
            try:
                # 加载任务相关数据
                task_data = await store.get_task_evidence_chain(task_id)
                if not task_data:
                    continue

                result = validator.validate(
                    claims=task_data.get("claims", []),
                    evidence=task_data.get("evidence", []),
                    chunks=task_data.get("chunks", []),
                    artifacts=task_data.get("artifacts", []),
                    report=task_data.get("report"),
                )
                results["checked"] += 1

                if result.is_valid:
                    results["passed"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].extend(
                        [
                            {"task_id": task_id, "error": e.message}
                            for e in result.errors[:5]  # 最多记录 5 个错误
                        ]
                    )
            except Exception as exc:
                logger.warning("检查失败: %s - %s", task_id, exc)
                results["errors"].append(
                    {
                        "task_id": task_id,
                        "error": str(exc),
                    }
                )

        await store.close()
        return results

    check_result = asyncio.run(_check())
    context["ti"].xcom_push(key="evidence_check", value=check_result)
    logger.info(
        "证据链检查: %d 通过, %d 失败",
        check_result["passed"],
        check_result["failed"],
    )
    return check_result


def _check_quality_rules(**context: Any) -> dict[str, Any]:
    """数据质量规则校验。"""
    import asyncio

    data = context["ti"].xcom_pull(key="recent_data", task_ids="load_data") or {}

    async def _check() -> dict[str, Any]:
        from baize_core.config.settings import get_settings
        from baize_core.quality.expectations import QualityGate
        from baize_core.storage.postgres import PostgresStore

        settings = get_settings()
        store = PostgresStore.from_dsn(settings.database_url)
        await store.connect()

        gate = QualityGate()
        results: dict[str, Any] = {
            "checked": 0,
            "passed": 0,
            "failed": 0,
            "violations": [],
        }

        # 检查 Artifact
        for artifact_uid in data.get("artifacts", []):
            try:
                artifact = await store.get_artifact(artifact_uid)
                if artifact:
                    result = gate.check_artifact(artifact)
                    results["checked"] += 1
                    if result.passed:
                        results["passed"] += 1
                    else:
                        results["failed"] += 1
                        results["violations"].extend(result.violations[:3])
            except Exception as exc:
                logger.warning("Artifact 检查失败: %s - %s", artifact_uid, exc)

        # 检查 Evidence
        for evidence_uid in data.get("evidence", []):
            try:
                evidence = await store.get_evidence(evidence_uid)
                if evidence:
                    result = gate.check_evidence(evidence)
                    results["checked"] += 1
                    if result.passed:
                        results["passed"] += 1
                    else:
                        results["failed"] += 1
                        results["violations"].extend(result.violations[:3])
            except Exception as exc:
                logger.warning("Evidence 检查失败: %s - %s", evidence_uid, exc)

        await store.close()
        return results

    check_result = asyncio.run(_check())
    context["ti"].xcom_push(key="quality_check", value=check_result)
    logger.info(
        "质量规则检查: %d 通过, %d 失败",
        check_result["passed"],
        check_result["failed"],
    )
    return check_result


def _decide_branch(**context: Any) -> str:
    """决定分支。"""
    evidence_check = (
        context["ti"].xcom_pull(key="evidence_check", task_ids="check_evidence_chain")
        or {}
    )
    quality_check = (
        context["ti"].xcom_pull(key="quality_check", task_ids="check_quality_rules")
        or {}
    )

    evidence_failed = evidence_check.get("failed", 0)
    quality_failed = quality_check.get("failed", 0)

    if evidence_failed > 0 or quality_failed > 0:
        return "send_alert"
    return "quality_passed"


def _send_alert(webhook: str, **context: Any) -> None:
    """发送告警。"""
    if not webhook:
        logger.info("告警 Webhook 未配置，跳过")
        return

    import asyncio

    import aiohttp

    evidence_check = (
        context["ti"].xcom_pull(key="evidence_check", task_ids="check_evidence_chain")
        or {}
    )
    quality_check = (
        context["ti"].xcom_pull(key="quality_check", task_ids="check_quality_rules")
        or {}
    )

    async def _send() -> None:
        message = {
            "title": "数据质量告警",
            "evidence_check": {
                "failed": evidence_check.get("failed", 0),
                "errors": evidence_check.get("errors", [])[:5],
            },
            "quality_check": {
                "failed": quality_check.get("failed", 0),
                "violations": quality_check.get("violations", [])[:5],
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(webhook, json=message) as resp:
                if resp.status != 200:
                    logger.warning("告警发送失败: %d", resp.status)
                else:
                    logger.info("告警已发送")

    asyncio.run(_send())


def _generate_quality_report(**context: Any) -> dict[str, Any]:
    """生成质量报告。"""
    import asyncio
    from uuid import uuid4

    evidence_check = (
        context["ti"].xcom_pull(key="evidence_check", task_ids="check_evidence_chain")
        or {}
    )
    quality_check = (
        context["ti"].xcom_pull(key="quality_check", task_ids="check_quality_rules")
        or {}
    )

    report = {
        "report_id": str(uuid4()),
        "generated_at": datetime.utcnow().isoformat(),
        "evidence_chain": {
            "checked": evidence_check.get("checked", 0),
            "passed": evidence_check.get("passed", 0),
            "failed": evidence_check.get("failed", 0),
            "pass_rate": (
                evidence_check.get("passed", 0)
                / max(evidence_check.get("checked", 1), 1)
            ),
        },
        "quality_rules": {
            "checked": quality_check.get("checked", 0),
            "passed": quality_check.get("passed", 0),
            "failed": quality_check.get("failed", 0),
            "pass_rate": (
                quality_check.get("passed", 0) / max(quality_check.get("checked", 1), 1)
            ),
        },
    }

    async def _save() -> None:
        from baize_core.config.settings import get_settings
        from baize_core.storage.postgres import PostgresStore

        settings = get_settings()
        store = PostgresStore.from_dsn(settings.database_url)
        await store.connect()
        await store.save_quality_report(report)
        await store.close()

    asyncio.run(_save())
    logger.info("质量报告已生成: %s", report["report_id"])
    return report


def _create_mock_dag(config: QualityConfig) -> dict[str, Any]:
    """创建模拟 DAG。"""
    return {
        "dag_id": config.dag_id,
        "schedule_interval": config.schedule_interval,
        "tasks": [
            "load_data",
            "check_evidence_chain",
            "check_quality_rules",
            "branch_on_result",
            "quality_passed",
            "send_alert",
            "generate_report",
        ],
        "mock": True,
    }
