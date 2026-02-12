"""可插拔分析阶段框架。

灵感来自 IntelOwl 的插件架构：stage 通过 ``__subclasses__()``
自动发现，由 Playbook 模板编排执行。
"""

from aegi_core.services.stages.base import AnalysisStage, StageContext, stage_registry
from aegi_core.services.stages.playbook import Playbook, load_playbooks

__all__ = [
    "AnalysisStage",
    "StageContext",
    "stage_registry",
    "Playbook",
    "load_playbooks",
]
