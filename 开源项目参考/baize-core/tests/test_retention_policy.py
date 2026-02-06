"""Retention policy 单元测试（不使用 mock/stub）。"""

from __future__ import annotations

from baize_core.retention.policy import resolve_retention_policy


def test_retention_policy_inheritance_project_then_task_override() -> None:
    config: dict[str, object] = {
        "retention_policy": {
            "defaults": {
                "task_retention_days": 30,
                "artifact_retention_days": 10,
                "chunk_retention_days": 10,
                "evidence_retention_days": 10,
                "hard_delete_grace_days": 7,
            },
            "projects": {
                "proj_a": {
                    "task_retention_days": 60,
                }
            },
        }
    }

    # project override
    policy = resolve_retention_policy(config=config, project_id="proj_a")
    assert policy.task_retention_days == 60
    # 未显式覆盖类型级保留时，仍使用 defaults
    assert policy.artifact_retention_days == 10

    # task override：覆盖“所有数据保留 N 天”
    policy2 = resolve_retention_policy(
        config=config, project_id="proj_a", task_retention_days=90
    )
    assert policy2.task_retention_days == 90
    assert policy2.artifact_retention_days == 90
    assert policy2.chunk_retention_days == 90
    assert policy2.evidence_retention_days == 90
