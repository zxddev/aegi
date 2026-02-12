"""可插拔分析阶段的抽象基类。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from aegi_core.services.pipeline_orchestrator import StageResult

logger = logging.getLogger(__name__)

# (stage_name, status, percent, message)
ProgressCallback = Callable[[str, str, float, str], Awaitable[None]]


@dataclass
class StageContext:
    """流水线各阶段间传递的可变数据包。"""

    case_uid: str
    source_claims: list = field(default_factory=list)
    assertions: list = field(default_factory=list)
    hypotheses: list = field(default_factory=list)
    narratives: list = field(default_factory=list)
    forecasts: list = field(default_factory=list)
    llm: Any = None
    neo4j: Any = None
    # 阶段专属配置覆盖（来自 Playbook）
    config: dict = field(default_factory=dict)
    # 进度回调，用于流式更新
    on_progress: ProgressCallback | None = None


class AnalysisStage(ABC):
    """所有流水线阶段的基类。

    子类通过 ``__subclasses__()`` 自动发现，按 ``name`` 属性注册。
    """

    name: str = ""  # 子类覆盖

    @abstractmethod
    async def run(self, ctx: StageContext) -> StageResult:
        """执行阶段，返回 StageResult。"""
        ...

    def should_skip(self, ctx: StageContext) -> str | None:
        """如果应跳过返回原因字符串，否则返回 None。"""
        return None


class _StageRegistry:
    """AnalysisStage 子类的自动发现注册表。"""

    def __init__(self) -> None:
        self._stages: dict[str, AnalysisStage] = {}
        self._discovered = False

    def _discover(self) -> None:
        """导入内置 stage 模块触发子类注册，然后收集。"""
        if self._discovered:
            return
        # 导入 stage 模块让子类完成注册
        import aegi_core.services.stages.builtin  # noqa: F401
        import aegi_core.services.stages.multi_perspective  # noqa: F401
        import aegi_core.services.stages.osint_collect  # noqa: F401

        for cls in AnalysisStage.__subclasses__():
            if cls.name:
                self._stages[cls.name] = cls()
        self._discovered = True
        logger.info("Discovered %d stages: %s", len(self._stages), list(self._stages))

    def get(self, name: str) -> AnalysisStage | None:
        self._discover()
        return self._stages.get(name)

    def all_names(self) -> list[str]:
        self._discover()
        return list(self._stages.keys())

    def register(self, stage: AnalysisStage) -> None:
        """手动注册 stage（用于第三方插件）。"""
        self._stages[stage.name] = stage
        logger.info("Registered stage: %s", stage.name)

    def ordered(self, names: list[str]) -> list[AnalysisStage]:
        """按给定顺序返回 stage 实例，跳过未知名称。"""
        self._discover()
        return [self._stages[n] for n in names if n in self._stages]


stage_registry = _StageRegistry()
