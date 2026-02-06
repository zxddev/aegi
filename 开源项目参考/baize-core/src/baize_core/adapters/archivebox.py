"""ArchiveBox 归档固化适配器。

ArchiveBox 是一个开源的网页归档工具，用于永久保存网页内容。
此适配器提供与 ArchiveBox API/CLI 的集成。
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx

from baize_core.schemas.evidence import Artifact

logger = logging.getLogger(__name__)


class ArchiveMethod(str, Enum):
    """归档方法。"""

    WGET = "wget"
    WGET_WARC = "wget_warc"
    SINGLEFILE = "singlefile"
    READABILITY = "readability"
    MERCURY = "mercury"
    PDF = "pdf"
    SCREENSHOT = "screenshot"
    DOM = "dom"
    GIT = "git"
    MEDIA = "media"


class ArchiveStatus(str, Enum):
    """归档状态。"""

    PENDING = "pending"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class ArchiveBoxConfig:
    """ArchiveBox 配置。"""

    # 使用 HTTP API 还是 Docker CLI
    use_api: bool = False
    # API 配置
    api_base_url: str | None = None
    api_key: str | None = None
    # Docker CLI 配置
    docker_container: str = "archivebox"
    docker_user: str = "archivebox"
    # 公开访问地址（用于生成归档 URL）
    public_host: str = "localhost"
    public_port: int = 8000
    # 超时配置
    timeout_seconds: int = 120
    # 默认归档方法
    default_methods: tuple[ArchiveMethod, ...] = (
        ArchiveMethod.WGET,
        ArchiveMethod.SINGLEFILE,
        ArchiveMethod.READABILITY,
    )


@dataclass
class ArchiveResult:
    """归档结果。"""

    url: str
    timestamp: str
    archive_url: str
    status: ArchiveStatus
    title: str | None = None
    content_hash: str | None = None
    mime_type: str = "text/html"
    methods_succeeded: list[ArchiveMethod] = field(default_factory=list)
    methods_failed: list[ArchiveMethod] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SnapshotInfo:
    """快照信息。"""

    url: str
    timestamp: str
    title: str | None
    tags: list[str]
    added: datetime
    updated: datetime
    archive_path: str
    status: ArchiveStatus


class ArchiveBoxClient:
    """ArchiveBox 客户端。

    支持功能：
    - 添加 URL 到归档
    - 查询归档状态
    - 获取快照列表
    - 生成 Artifact 记录
    """

    def __init__(self, config: ArchiveBoxConfig) -> None:
        """初始化客户端。

        Args:
            config: ArchiveBox 配置
        """
        self._config = config

    async def add(
        self,
        url: str,
        *,
        depth: int = 0,
        methods: list[ArchiveMethod] | None = None,
        tags: list[str] | None = None,
    ) -> ArchiveResult:
        """添加 URL 到归档。

        Args:
            url: 要归档的 URL
            depth: 抓取深度（0 = 仅当前页面）
            methods: 归档方法列表
            tags: 标签列表

        Returns:
            归档结果
        """
        if self._config.use_api:
            return await self._add_via_api(url, depth=depth, methods=methods, tags=tags)
        return await self._add_via_cli(url, depth=depth, methods=methods, tags=tags)

    async def get_status(self, timestamp: str) -> ArchiveResult | None:
        """获取归档状态。

        Args:
            timestamp: 归档时间戳

        Returns:
            归档结果，不存在返回 None
        """
        if self._config.use_api:
            return await self._get_status_via_api(timestamp)
        return await self._get_status_via_cli(timestamp)

    async def list_snapshots(
        self,
        *,
        tag: str | None = None,
        limit: int = 100,
    ) -> list[SnapshotInfo]:
        """列出快照。

        Args:
            tag: 按标签过滤
            limit: 最大返回数量

        Returns:
            快照列表
        """
        if self._config.use_api:
            return await self._list_via_api(tag=tag, limit=limit)
        return await self._list_via_cli(tag=tag, limit=limit)

    async def add_and_create_artifact(
        self,
        url: str,
        *,
        depth: int = 0,
        methods: list[ArchiveMethod] | None = None,
        tags: list[str] | None = None,
    ) -> Artifact:
        """添加 URL 到归档并创建 Artifact 记录。

        Args:
            url: 要归档的 URL
            depth: 抓取深度
            methods: 归档方法列表
            tags: 标签列表

        Returns:
            Artifact 记录
        """
        result = await self.add(url, depth=depth, methods=methods, tags=tags)

        # 解析时间戳
        try:
            fetched_at = datetime.strptime(result.timestamp, "%Y%m%d%H%M%S").replace(
                tzinfo=UTC
            )
        except ValueError:
            fetched_at = datetime.now(UTC)

        # 构建存储引用
        storage_ref = result.archive_url

        # 内容哈希（使用时间戳作为备选）
        content_hash = result.content_hash or f"archivebox_{result.timestamp}"

        return Artifact(
            artifact_uid=f"art_{result.timestamp}",
            source_url=url,
            fetched_at=fetched_at,
            content_sha256=f"sha256:{content_hash}",
            mime_type=result.mime_type,
            storage_ref=storage_ref,
            origin_tool="archivebox",
        )

    async def _add_via_api(
        self,
        url: str,
        *,
        depth: int = 0,
        methods: list[ArchiveMethod] | None = None,
        tags: list[str] | None = None,
    ) -> ArchiveResult:
        """通过 API 添加 URL。"""
        if not self._config.api_base_url:
            raise ValueError("API base URL 未配置")

        endpoint = f"{self._config.api_base_url}/api/v1/add"
        payload: dict[str, Any] = {
            "urls": [url],
            "depth": depth,
        }
        if methods:
            payload["extractors"] = ",".join(m.value for m in methods)
        if tags:
            payload["tag"] = ",".join(tags)

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
        ) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return self._parse_api_result(url, data)

    async def _add_via_cli(
        self,
        url: str,
        *,
        depth: int = 0,
        methods: list[ArchiveMethod] | None = None,
        tags: list[str] | None = None,
    ) -> ArchiveResult:
        """通过 Docker CLI 添加 URL。"""
        command = [
            "docker",
            "exec",
            "--user",
            self._config.docker_user,
            self._config.docker_container,
            "archivebox",
            "add",
            "--json",
        ]

        if depth > 0:
            command.extend(["--depth", str(depth)])

        if methods:
            extractors = ",".join(m.value for m in methods)
            command.extend(["--extract", extractors])

        if tags:
            for tag in tags:
                command.extend(["--tag", tag])

        command.append(url)

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )

        result = await asyncio.to_thread(_run)

        if result.returncode != 0:
            logger.error("ArchiveBox CLI 失败: %s", result.stderr)
            raise RuntimeError(result.stderr.strip() or "ArchiveBox 执行失败")

        return self._parse_cli_result(url, result.stdout)

    async def _get_status_via_api(self, timestamp: str) -> ArchiveResult | None:
        """通过 API 获取状态。"""
        if not self._config.api_base_url:
            raise ValueError("API base URL 未配置")

        endpoint = f"{self._config.api_base_url}/api/v1/snapshots/{timestamp}"
        headers: dict[str, str] = {}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        async with httpx.AsyncClient(
            timeout=30,
        ) as client:
            response = await client.get(endpoint, headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return self._parse_api_status(data)

    async def _get_status_via_cli(self, timestamp: str) -> ArchiveResult | None:
        """通过 CLI 获取状态。"""
        command = [
            "docker",
            "exec",
            "--user",
            self._config.docker_user,
            self._config.docker_container,
            "archivebox",
            "status",
            "--json",
            timestamp,
        ]

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )

        result = await asyncio.to_thread(_run)
        if result.returncode != 0:
            return None

        return self._parse_cli_status(result.stdout)

    async def _list_via_api(
        self,
        tag: str | None = None,
        limit: int = 100,
    ) -> list[SnapshotInfo]:
        """通过 API 列出快照。"""
        if not self._config.api_base_url:
            raise ValueError("API base URL 未配置")

        endpoint = f"{self._config.api_base_url}/api/v1/snapshots"
        params: dict[str, Any] = {"limit": limit}
        if tag:
            params["tag"] = tag

        headers: dict[str, str] = {}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return [self._parse_snapshot_info(item) for item in data.get("items", [])]

    async def _list_via_cli(
        self,
        tag: str | None = None,
        limit: int = 100,
    ) -> list[SnapshotInfo]:
        """通过 CLI 列出快照。"""
        command = [
            "docker",
            "exec",
            "--user",
            self._config.docker_user,
            self._config.docker_container,
            "archivebox",
            "list",
            "--json",
        ]

        if tag:
            command.extend(["--filter-tag", tag])

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )

        result = await asyncio.to_thread(_run)
        if result.returncode != 0:
            logger.warning("ArchiveBox list 失败: %s", result.stderr)
            return []

        snapshots: list[SnapshotInfo] = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if isinstance(data, list):
                    for item in data[:limit]:
                        snapshots.append(self._parse_snapshot_info(item))
                elif isinstance(data, dict):
                    snapshots.append(self._parse_snapshot_info(data))
            except json.JSONDecodeError:
                continue

        return snapshots[:limit]

    def _parse_api_result(self, url: str, data: dict[str, Any]) -> ArchiveResult:
        """解析 API 响应。"""
        result_data = data.get("result", data)
        timestamp = result_data.get("timestamp", "")
        archive_url = self._build_archive_url(timestamp)

        return ArchiveResult(
            url=url,
            timestamp=timestamp,
            archive_url=archive_url,
            status=ArchiveStatus.SUCCEEDED,
            title=result_data.get("title"),
            content_hash=result_data.get("hash"),
            metadata=result_data,
        )

    def _parse_cli_result(self, url: str, stdout: str) -> ArchiveResult:
        """解析 CLI 输出。"""
        payload: dict[str, Any] | None = None
        lines = [line for line in stdout.splitlines() if line.strip()]

        for line in lines:
            try:
                data = json.loads(line)
                if isinstance(data, list) and data:
                    payload = data[0] if isinstance(data[0], dict) else None
                    break
                if isinstance(data, dict):
                    payload = data
                    break
            except json.JSONDecodeError:
                continue

        if payload is None:
            raise RuntimeError("ArchiveBox 输出缺少 JSON")

        timestamp = self._extract_field(payload, "timestamp")
        archive_url = self._build_archive_url(timestamp)

        return ArchiveResult(
            url=url,
            timestamp=timestamp,
            archive_url=archive_url,
            status=ArchiveStatus.SUCCEEDED,
            title=payload.get("title"),
            content_hash=payload.get("content_sha256") or payload.get("hash"),
            mime_type=payload.get("mime_type", "text/html"),
            metadata=payload,
        )

    def _parse_api_status(self, data: dict[str, Any]) -> ArchiveResult:
        """解析 API 状态响应。"""
        timestamp = data.get("timestamp", "")
        archive_url = self._build_archive_url(timestamp)
        status_str = data.get("status", "succeeded")

        try:
            status = ArchiveStatus(status_str.lower())
        except ValueError:
            status = ArchiveStatus.SUCCEEDED

        return ArchiveResult(
            url=data.get("url", ""),
            timestamp=timestamp,
            archive_url=archive_url,
            status=status,
            title=data.get("title"),
            content_hash=data.get("hash"),
            metadata=data,
        )

    def _parse_cli_status(self, stdout: str) -> ArchiveResult | None:
        """解析 CLI 状态输出。"""
        try:
            for line in stdout.strip().split("\n"):
                if line.strip():
                    data = json.loads(line)
                    return self._parse_api_status(data)
        except json.JSONDecodeError:
            pass
        return None

    def _parse_snapshot_info(self, data: dict[str, Any]) -> SnapshotInfo:
        """解析快照信息。"""
        timestamp = data.get("timestamp", "")
        added_raw = data.get("added") or data.get("timestamp") or ""
        added_str = added_raw if isinstance(added_raw, str) else str(added_raw)
        updated_raw = data.get("updated") or added_str
        updated_str = updated_raw if isinstance(updated_raw, str) else str(updated_raw)

        try:
            added = datetime.fromisoformat(added_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            added = datetime.now(UTC)

        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            updated = added

        status_str = data.get("status", "succeeded")
        try:
            status = ArchiveStatus(status_str.lower())
        except ValueError:
            status = ArchiveStatus.SUCCEEDED

        return SnapshotInfo(
            url=data.get("url", ""),
            timestamp=timestamp,
            title=data.get("title"),
            tags=data.get("tags", []),
            added=added,
            updated=updated,
            archive_path=self._build_archive_url(timestamp),
            status=status,
        )

    def _build_archive_url(self, timestamp: str) -> str:
        """构建归档 URL。"""
        host = self._config.public_host
        port = self._config.public_port
        return f"http://{host}:{port}/archive/{timestamp}/"

    def _extract_field(self, payload: dict[str, Any], *keys: str) -> str:
        """提取字段值。"""
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise RuntimeError(f"ArchiveBox 输出缺少必要字段: {keys}")


def create_archivebox_client(
    *,
    docker_container: str = "archivebox",
    docker_user: str = "archivebox",
    public_host: str = "localhost",
    public_port: int = 8000,
) -> ArchiveBoxClient:
    """创建 ArchiveBox 客户端的便捷函数（Docker CLI 模式）。

    Args:
        docker_container: Docker 容器名
        docker_user: Docker 用户
        public_host: 公开访问主机
        public_port: 公开访问端口

    Returns:
        ArchiveBox 客户端实例
    """
    config = ArchiveBoxConfig(
        use_api=False,
        docker_container=docker_container,
        docker_user=docker_user,
        public_host=public_host,
        public_port=public_port,
    )
    return ArchiveBoxClient(config)


def create_archivebox_api_client(
    api_base_url: str,
    api_key: str | None = None,
    public_host: str = "localhost",
    public_port: int = 8000,
) -> ArchiveBoxClient:
    """创建 ArchiveBox 客户端的便捷函数（API 模式）。

    Args:
        api_base_url: API 地址
        api_key: API Key
        public_host: 公开访问主机
        public_port: 公开访问端口

    Returns:
        ArchiveBox 客户端实例
    """
    config = ArchiveBoxConfig(
        use_api=True,
        api_base_url=api_base_url,
        api_key=api_key,
        public_host=public_host,
        public_port=public_port,
    )
    return ArchiveBoxClient(config)
