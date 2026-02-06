"""工具注册表加载与热重载。"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class ToolRateLimitConfig(BaseModel):
    """工具级限流配置。"""

    requests_per_second: float = Field(default=10.0, gt=0)
    burst_size: int = Field(default=20, gt=0)


class ToolConfig(BaseModel):
    """工具配置。"""

    url: str = Field(min_length=1)
    method: str = Field(default="POST")
    adapter: str | None = None
    # 工具级配置增强
    allowed_roles: list[str] = Field(default_factory=list)
    rate_limit: ToolRateLimitConfig | None = None
    timeout_ms: int | None = Field(default=None, gt=0)
    # 风险等级（用于审计和 HITL 判断）
    risk_level: str = Field(default="low")
    # 是否需要人工确认
    require_human_review: bool = Field(default=False)
    # 描述（用于文档）
    description: str = Field(default="")

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        """校验请求方法。"""

        upper = value.upper()
        if upper not in {"POST", "GET"}:
            raise ValueError("仅支持 POST/GET")
        return upper

    @field_validator("adapter")
    @classmethod
    def validate_adapter(cls, value: str | None) -> str | None:
        """校验适配器类型。"""

        if value is None:
            return None
        if value not in {"searxng", "unstructured", "archivebox", "firecrawl"}:
            raise ValueError("仅支持 searxng/unstructured/archivebox/firecrawl 适配器")
        return value

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, value: str) -> str:
        """校验风险等级。"""

        lower = value.lower()
        if lower not in {"low", "medium", "high"}:
            raise ValueError("仅支持 low/medium/high 风险等级")
        return lower

    def get_timeout_seconds(self, default_timeout_ms: int) -> float:
        """获取超时时间（秒）。"""
        timeout_ms = self.timeout_ms or default_timeout_ms
        return timeout_ms / 1000.0


class ToolRegistry(BaseModel):
    """工具注册表。"""

    tools: dict[str, ToolConfig] = Field(default_factory=dict)


@dataclass
class LoadedRegistry:
    """注册表加载结果。"""

    tools: dict[str, ToolConfig]
    # 文件路径（用于热重载）
    _path: Path | None = field(default=None, repr=False)
    # 上次加载时间
    _last_loaded: float = field(default=0.0, repr=False)
    # 读写锁
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)


def load_registry(path: Path) -> LoadedRegistry:
    """加载工具注册表。"""

    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("工具注册表 JSON 无法解析") from exc
    registry = ToolRegistry.model_validate(payload)
    import time

    return LoadedRegistry(
        tools=registry.tools,
        _path=path,
        _last_loaded=time.time(),
    )


class RegistryReloader:
    """工具注册表热重载管理器。

    支持：
    - 文件变更监控（使用 watchfiles）
    - 原子性配置更新
    - 手动重载端点
    - 重载回调（用于更新限流器等）
    """

    def __init__(
        self,
        registry: LoadedRegistry,
        on_reload: Callable[[LoadedRegistry], None] | None = None,
    ) -> None:
        """初始化重载管理器。

        Args:
            registry: 已加载的注册表
            on_reload: 重载成功后的回调函数
        """
        self._registry = registry
        self._on_reload = on_reload
        self._watch_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def registry(self) -> LoadedRegistry:
        """获取当前注册表。"""
        return self._registry

    def reload(self) -> LoadedRegistry:
        """同步重载注册表。

        Returns:
            新的注册表

        Raises:
            ValueError: 重载失败
        """
        if self._registry._path is None:
            raise ValueError("注册表路径未知，无法重载")

        path = self._registry._path
        logger.info("开始重载工具注册表: %s", path)

        try:
            new_registry = load_registry(path)
        except Exception as exc:
            logger.error("重载工具注册表失败: %s", exc)
            raise ValueError(f"重载失败: {exc}") from exc

        # 原子性更新
        with self._registry._lock:
            old_tools = set(self._registry.tools.keys())
            new_tools = set(new_registry.tools.keys())
            added = new_tools - old_tools
            removed = old_tools - new_tools
            updated = old_tools & new_tools

            self._registry.tools = new_registry.tools
            self._registry._last_loaded = new_registry._last_loaded

        logger.info(
            "工具注册表已重载: 新增=%d, 移除=%d, 更新=%d",
            len(added),
            len(removed),
            len(updated),
        )

        if self._on_reload is not None:
            try:
                self._on_reload(self._registry)
            except Exception as exc:
                logger.warning("重载回调执行失败: %s", exc)

        return self._registry

    async def start_watch(self) -> None:
        """启动文件监控。"""
        if self._registry._path is None:
            logger.warning("注册表路径未知，无法启动文件监控")
            return

        try:
            import watchfiles
        except ImportError:
            logger.warning("watchfiles 未安装，文件监控不可用")
            return

        path = self._registry._path
        self._stop_event.clear()

        async def _watch() -> None:
            try:
                async for changes in watchfiles.awatch(
                    path,
                    stop_event=self._stop_event,
                ):
                    logger.info("检测到配置文件变更: %s", changes)
                    try:
                        self.reload()
                    except Exception as exc:
                        logger.error("自动重载失败: %s", exc)
            except asyncio.CancelledError:
                pass

        self._watch_task = asyncio.create_task(_watch())
        logger.info("文件监控已启动: %s", path)

    async def stop_watch(self) -> None:
        """停止文件监控。"""
        self._stop_event.set()
        if self._watch_task is not None:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            self._watch_task = None
        logger.info("文件监控已停止")

    def get_stats(self) -> dict[str, object]:
        """获取统计信息。"""
        import time

        return {
            "path": str(self._registry._path) if self._registry._path else None,
            "tool_count": len(self._registry.tools),
            "last_loaded": self._registry._last_loaded,
            "seconds_since_load": time.time() - self._registry._last_loaded,
            "watching": self._watch_task is not None and not self._watch_task.done(),
        }
