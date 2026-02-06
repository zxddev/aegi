from __future__ import annotations

import os
from typing import cast
from uuid import uuid4

import pytest

from baize_core.config.settings import AppConfig
from baize_core.orchestration.factory import build_orchestrator
from baize_core.schemas.evidence import Report
from baize_core.schemas.review import ReviewResult
from baize_core.schemas.storm import ReportConfig
from baize_core.schemas.task import TaskSpec


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("DEFAULT_LLM_PROVIDER"),
    reason="需要配置 DEFAULT_LLM_PROVIDER 等环境变量",
)
async def test_storm_end_to_end() -> None:
    config = AppConfig.from_env()
    orchestrator = build_orchestrator(config)
    task = TaskSpec(
        task_id=f"storm-e2e-{uuid4().hex}",
        # 使用更通用的查询，避免依赖需要认证的 defense.gov PDF
        objective="Taiwan Strait recent military developments",
    )
    result = await orchestrator.run_storm(
        task=task,
        report_config=ReportConfig(title="STORM 研究报告"),
    )
    report_record = cast(Report | None, result.get("report_record"))
    review = cast(ReviewResult | None, result.get("review"))
    assert report_record is not None
    assert review is not None
    # 当 BAIZE_SKIP_REVIEW_VALIDATION=true 时，即使 review.ok=False 也不会抛异常
    # 只检查报告已成功生成并存储
    assert report_record.content_ref.startswith("minio://")
