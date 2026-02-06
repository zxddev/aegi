"""changedetection.io 适配器。

提供网页变更监测能力：
- 添加监测 URL
- 获取变更通知
- 变更内容抓取并生成 Artifact
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ChangeDetectionConfig:
    """changedetection.io 配置。"""

    base_url: str = "http://localhost:5000"
    api_key: str = ""
    timeout: int = 30


@dataclass
class WatchTarget:
    """监测目标。"""

    url: str
    title: str = ""
    tag: str = ""
    check_interval: int = 3600  # 检查间隔（秒）
    headers: dict[str, str] = field(default_factory=dict)
    css_filter: str = ""  # CSS 选择器过滤
    xpath_filter: str = ""  # XPath 过滤


@dataclass
class ChangeRecord:
    """变更记录。"""

    watch_uuid: str
    url: str
    title: str
    changed_at: datetime
    previous_hash: str
    current_hash: str
    diff_text: str = ""
    snapshot_url: str = ""


class ChangeDetectionClient:
    """changedetection.io API 客户端。"""

    def __init__(self, config: ChangeDetectionConfig) -> None:
        """初始化客户端。

        Args:
            config: 配置
        """
        self._config = config
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        """建立连接。"""
        headers = {
            "Content-Type": "application/json",
        }
        if self._config.api_key:
            headers["x-api-key"] = self._config.api_key

        timeout = aiohttp.ClientTimeout(total=self._config.timeout)
        self._session = aiohttp.ClientSession(
            headers=headers,
            timeout=timeout,
        )
        logger.info("ChangeDetection 客户端已连接: %s", self._config.base_url)

    async def close(self) -> None:
        """关闭连接。"""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("ChangeDetection 客户端已关闭")

    async def __aenter__(self) -> ChangeDetectionClient:
        """异步上下文管理器入口。"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口。"""
        await self.close()

    # ============ 监测管理 ============

    async def add_watch(self, target: WatchTarget) -> str:
        """添加监测目标。

        Args:
            target: 监测目标

        Returns:
            监测 UUID
        """
        payload = {
            "url": target.url,
            "title": target.title or target.url,
            "tag": target.tag,
            "time_between_check": {"minutes": target.check_interval // 60},
        }

        if target.headers:
            payload["headers"] = target.headers
        if target.css_filter:
            payload["css_filter"] = target.css_filter
        if target.xpath_filter:
            payload["xpath_filter"] = target.xpath_filter

        result = await self._post("/api/v1/watch", payload)
        watch_uuid = result.get("uuid", "")
        logger.info("添加监测目标: %s -> %s", target.url, watch_uuid)
        return watch_uuid

    async def delete_watch(self, watch_uuid: str) -> None:
        """删除监测目标。"""
        await self._delete(f"/api/v1/watch/{watch_uuid}")
        logger.info("删除监测目标: %s", watch_uuid)

    async def list_watches(self) -> list[dict[str, Any]]:
        """列出所有监测目标。"""
        result = await self._get("/api/v1/watch")
        return list(result.values()) if isinstance(result, dict) else result

    async def get_watch(self, watch_uuid: str) -> dict[str, Any]:
        """获取监测目标详情。"""
        return await self._get(f"/api/v1/watch/{watch_uuid}")

    async def trigger_check(self, watch_uuid: str) -> None:
        """触发立即检查。"""
        await self._get(f"/api/v1/watch/{watch_uuid}/trigger-check")
        logger.info("触发检查: %s", watch_uuid)

    # ============ 变更查询 ============

    async def get_changes(
        self,
        since: datetime | None = None,
    ) -> list[ChangeRecord]:
        """获取变更记录。

        Args:
            since: 只获取此时间之后的变更

        Returns:
            变更记录列表
        """
        watches = await self.list_watches()
        changes: list[ChangeRecord] = []

        for watch in watches:
            watch_uuid = watch.get("uuid", "")
            last_changed = watch.get("last_changed")

            if not last_changed:
                continue

            changed_at = datetime.fromtimestamp(last_changed, tz=UTC)
            if since and changed_at <= since:
                continue

            history = await self.get_history(watch_uuid)
            if not history:
                continue

            latest = history[0] if history else {}
            changes.append(
                ChangeRecord(
                    watch_uuid=watch_uuid,
                    url=watch.get("url", ""),
                    title=watch.get("title", ""),
                    changed_at=changed_at,
                    previous_hash=latest.get("previous_hash", ""),
                    current_hash=latest.get("current_hash", ""),
                    diff_text=latest.get("diff_text", ""),
                    snapshot_url=f"{self._config.base_url}/api/v1/watch/{watch_uuid}/snapshot",
                )
            )

        return changes

    async def get_history(
        self,
        watch_uuid: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """获取监测历史。"""
        result = await self._get(f"/api/v1/watch/{watch_uuid}/history")
        history_list = list(result.values()) if isinstance(result, dict) else result
        return history_list[:limit]

    async def get_snapshot(self, watch_uuid: str) -> str:
        """获取最新快照内容。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._config.base_url}/api/v1/watch/{watch_uuid}/snapshot"
        async with self._session.get(url) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取快照失败: {resp.status} - {text}")
            return await resp.text()

    async def get_diff(
        self,
        watch_uuid: str,
        history_timestamp: int | None = None,
    ) -> str:
        """获取变更差异。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._config.base_url}/api/v1/watch/{watch_uuid}/diff"
        if history_timestamp:
            url += f"?history_timestamp={history_timestamp}"

        async with self._session.get(url) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取差异失败: {resp.status} - {text}")
            return await resp.text()

    # ============ 内部方法 ============

    async def _get(self, path: str) -> Any:
        """发送 GET 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._config.base_url}{path}"
        async with self._session.get(url) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"ChangeDetection API 错误: {resp.status} - {text}")
            return await resp.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送 POST 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._config.base_url}{path}"
        async with self._session.post(url, json=payload) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"ChangeDetection API 错误: {resp.status} - {text}")
            return await resp.json()

    async def _delete(self, path: str) -> None:
        """发送 DELETE 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._config.base_url}{path}"
        async with self._session.delete(url) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"ChangeDetection API 错误: {resp.status} - {text}")


async def fetch_changes(
    base_url: str,
    api_key: str,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """获取变更记录（便捷函数）。

    Args:
        base_url: API 基地址
        api_key: API 密钥
        since: 只获取此时间之后的变更

    Returns:
        变更记录列表
    """
    config = ChangeDetectionConfig(base_url=base_url, api_key=api_key)
    async with ChangeDetectionClient(config) as client:
        changes = await client.get_changes(since=since)
        return [
            {
                "watch_uuid": c.watch_uuid,
                "url": c.url,
                "title": c.title,
                "changed_at": c.changed_at.isoformat(),
                "diff_text": c.diff_text,
                "source": "changedetection",
            }
            for c in changes
        ]


def get_changedetection_config_from_env() -> ChangeDetectionConfig:
    """从环境变量获取配置。"""
    import os

    return ChangeDetectionConfig(
        base_url=os.getenv("CHANGEDETECTION_URL", "http://localhost:5000"),
        api_key=os.getenv("CHANGEDETECTION_API_KEY", ""),
        timeout=int(os.getenv("CHANGEDETECTION_TIMEOUT", "30")),
    )
