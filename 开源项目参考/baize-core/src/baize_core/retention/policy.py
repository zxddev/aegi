"""Retention policy（数据保留策略）。

说明：
- 本模块只负责“策略解析/继承/决策”，不执行实际删除。
- 策略继承：global → project → task
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RetentionPolicy:
    """已解析的保留策略。"""

    # task 级：如果配置了 task_retention_days，则视为“该任务下所有数据保留 N 天”
    task_retention_days: int
    # 类型级（global/project 默认）
    artifact_retention_days: int
    chunk_retention_days: int
    evidence_retention_days: int
    # 软删到物理删除的宽限期（天）
    hard_delete_grace_days: int


def default_policy_path() -> Path:
    """默认保留策略配置路径。"""

    return Path(__file__).resolve().parent.parent / "config" / "retention_policy.yaml"


def load_retention_policy_config(path: Path | None = None) -> dict[str, object]:
    """加载 YAML 配置。"""

    if path:
        config_path = path
    else:
        env_path = os.getenv("BAIZE_RETENTION_POLICY_PATH", "").strip()
        config_path = Path(env_path) if env_path else default_policy_path()
    if not config_path.exists() or not config_path.is_file():
        raise FileNotFoundError(f"retention policy 配置文件不存在: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("retention policy 配置必须为 YAML dict")
    return data


def resolve_retention_policy(
    *,
    config: dict[str, object] | None = None,
    project_id: str | None = None,
    task_retention_days: int | None = None,
) -> RetentionPolicy:
    """解析策略（global → project → task）。"""

    cfg = config or load_retention_policy_config()
    root = cfg.get("retention_policy")
    if not isinstance(root, dict):
        raise ValueError("配置缺少 retention_policy 根节点")

    defaults = root.get("defaults")
    if not isinstance(defaults, dict):
        raise ValueError("配置缺少 retention_policy.defaults")

    merged: dict[str, Any] = dict(defaults)

    projects = root.get("projects")
    if project_id and isinstance(projects, dict):
        proj = projects.get(project_id)
        if isinstance(proj, dict):
            merged.update(proj)

    # task 覆盖：当 task_retention_days 存在时，视为“所有数据保留 N 天”
    if task_retention_days is not None:
        if task_retention_days <= 0:
            raise ValueError("task_retention_days 必须大于 0")
        merged["task_retention_days"] = task_retention_days
        merged["artifact_retention_days"] = task_retention_days
        merged["chunk_retention_days"] = task_retention_days
        merged["evidence_retention_days"] = task_retention_days

    return RetentionPolicy(
        task_retention_days=_require_positive_int(merged, "task_retention_days"),
        artifact_retention_days=_require_positive_int(
            merged, "artifact_retention_days"
        ),
        chunk_retention_days=_require_positive_int(merged, "chunk_retention_days"),
        evidence_retention_days=_require_positive_int(
            merged, "evidence_retention_days"
        ),
        hard_delete_grace_days=_require_positive_int(merged, "hard_delete_grace_days"),
    )


def _require_positive_int(mapping: dict[str, Any], key: str) -> int:
    value = mapping.get(key)
    if value is None:
        raise ValueError(f"retention policy 缺少必填字段: {key}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"retention policy 字段 {key} 必须为整数") from exc
    if parsed <= 0:
        raise ValueError(f"retention policy 字段 {key} 必须大于 0")
    return parsed
