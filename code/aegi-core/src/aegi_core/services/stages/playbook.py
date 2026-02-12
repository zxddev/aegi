"""Playbook：命名的流水线配置。

定义要运行哪些 stage 以及可选的 per-stage 配置覆盖。
从 YAML 加载或编程创建。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 默认 stage 顺序（与原始 STAGE_ORDER 一致）
DEFAULT_STAGES = [
    "assertion_fuse",
    "hypothesis_analyze",
    "adversarial_evaluate",
    "narrative_build",
    "kg_build",
    "forecast_generate",
    "quality_score",
    "report_generate",
]


@dataclass
class Playbook:
    """命名的流水线配置。"""

    name: str
    description: str = ""
    stages: list[str] = field(default_factory=lambda: list(DEFAULT_STAGES))
    stage_config: dict[str, dict[str, Any]] = field(default_factory=dict)

    @staticmethod
    def default() -> Playbook:
        return Playbook(name="default", description="Full 8-stage analysis pipeline")


# 全局 playbook 存储
_playbooks: dict[str, Playbook] = {}


def load_playbooks(path: str | Path) -> dict[str, Playbook]:
    """从 YAML 文件加载 playbooks，返回 name→Playbook 映射。"""
    p = Path(path)
    if not p.exists():
        logger.warning("Playbook file not found: %s", p)
        return {}

    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "playbooks" not in data:
        return {}

    for entry in data["playbooks"]:
        pb = Playbook(
            name=entry["name"],
            description=entry.get("description", ""),
            stages=entry.get("stages", list(DEFAULT_STAGES)),
            stage_config=entry.get("stage_config", {}),
        )
        _playbooks[pb.name] = pb
        logger.info("Loaded playbook: %s (%d stages)", pb.name, len(pb.stages))

    return dict(_playbooks)


def get_playbook(name: str) -> Playbook:
    """按名称获取 playbook，找不到时返回默认。"""
    return _playbooks.get(name, Playbook.default())


def list_playbooks() -> list[str]:
    """返回所有已注册的 playbook 名称。"""
    return list(_playbooks.keys())
