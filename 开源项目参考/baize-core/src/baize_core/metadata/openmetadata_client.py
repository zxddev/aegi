"""OpenMetadata API 客户端。

- 数据源注册 (Postgres, MinIO, OpenSearch)
- 血缘追踪 (Artifact -> Chunk -> Evidence)
- 标签与责任人管理
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class OpenMetadataConfig:
    """OpenMetadata 配置。"""

    server_url: str = "http://localhost:8585/api"
    api_version: str = "v1"
    auth_token: str = ""
    timeout: int = 30


@dataclass
class DataSource:
    """数据源定义。"""

    name: str
    service_type: str  # Postgres, MinIO, OpenSearch, etc.
    connection_config: dict[str, Any]
    description: str = ""
    tags: list[str] = field(default_factory=list)
    owner: str = ""


@dataclass
class LineageEdge:
    """血缘边定义。"""

    from_entity_type: str
    from_entity_fqn: str
    to_entity_type: str
    to_entity_fqn: str
    description: str = ""


@dataclass
class Tag:
    """标签定义。"""

    name: str
    description: str = ""
    category: str = "default"


class OpenMetadataClient:
    """OpenMetadata API 客户端。"""

    def __init__(self, config: OpenMetadataConfig) -> None:
        """初始化客户端。

        Args:
            config: OpenMetadata 配置
        """
        self._config = config
        self._base_url = f"{config.server_url}/{config.api_version}"
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        """建立连接。"""
        headers = {
            "Content-Type": "application/json",
        }
        if self._config.auth_token:
            headers["Authorization"] = f"Bearer {self._config.auth_token}"

        timeout = aiohttp.ClientTimeout(total=self._config.timeout)
        self._session = aiohttp.ClientSession(
            headers=headers,
            timeout=timeout,
        )
        logger.info("OpenMetadata 客户端已连接: %s", self._config.server_url)

    async def close(self) -> None:
        """关闭连接。"""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("OpenMetadata 客户端已关闭")

    async def __aenter__(self) -> OpenMetadataClient:
        """异步上下文管理器入口。"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口。"""
        await self.close()

    # ============ 数据源管理 ============

    async def register_postgres_source(
        self,
        name: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        description: str = "",
    ) -> dict[str, Any]:
        """注册 PostgreSQL 数据源。"""
        payload = {
            "name": name,
            "serviceType": "Postgres",
            "description": description,
            "connection": {
                "config": {
                    "type": "Postgres",
                    "hostPort": f"{host}:{port}",
                    "database": database,
                    "username": username,
                    "password": password,
                }
            },
        }
        return await self._post("/services/databaseServices", payload)

    async def register_minio_source(
        self,
        name: str,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_names: list[str],
        description: str = "",
    ) -> dict[str, Any]:
        """注册 MinIO 数据源。"""
        payload = {
            "name": name,
            "serviceType": "S3",
            "description": description,
            "connection": {
                "config": {
                    "type": "S3",
                    "awsConfig": {
                        "awsAccessKeyId": access_key,
                        "awsSecretAccessKey": secret_key,
                        "endPointURL": endpoint,
                    },
                    "bucketNames": bucket_names,
                }
            },
        }
        return await self._post("/services/storageServices", payload)

    async def register_opensearch_source(
        self,
        name: str,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """注册 OpenSearch 数据源。"""
        payload = {
            "name": name,
            "serviceType": "ElasticSearch",
            "description": description,
            "connection": {
                "config": {
                    "type": "ElasticSearch",
                    "hostPort": f"{host}:{port}",
                    "username": username or None,
                    "password": password or None,
                }
            },
        }
        return await self._post("/services/searchServices", payload)

    async def list_database_services(self) -> list[dict[str, Any]]:
        """列出所有数据库服务。"""
        result = await self._get("/services/databaseServices")
        return result.get("data", [])

    async def list_storage_services(self) -> list[dict[str, Any]]:
        """列出所有存储服务。"""
        result = await self._get("/services/storageServices")
        return result.get("data", [])

    # ============ 血缘追踪 ============

    async def add_lineage(
        self,
        from_entity_type: str,
        from_entity_fqn: str,
        to_entity_type: str,
        to_entity_fqn: str,
        description: str = "",
    ) -> dict[str, Any]:
        """添加血缘关系。

        Args:
            from_entity_type: 来源实体类型（table, container, etc.）
            from_entity_fqn: 来源实体全限定名
            to_entity_type: 目标实体类型
            to_entity_fqn: 目标实体全限定名
            description: 描述

        Returns:
            创建的血缘关系
        """
        payload = {
            "edge": {
                "fromEntity": {
                    "type": from_entity_type,
                    "fqn": from_entity_fqn,
                },
                "toEntity": {
                    "type": to_entity_type,
                    "fqn": to_entity_fqn,
                },
                "description": description,
            }
        }
        return await self._put("/lineage", payload)

    async def add_evidence_chain_lineage(
        self,
        artifact_fqn: str,
        chunk_fqn: str,
        evidence_fqn: str,
    ) -> list[dict[str, Any]]:
        """添加证据链血缘关系。

        Artifact -> Chunk -> Evidence

        Args:
            artifact_fqn: Artifact 全限定名
            chunk_fqn: Chunk 全限定名
            evidence_fqn: Evidence 全限定名

        Returns:
            创建的血缘关系列表
        """
        results = []

        # Artifact -> Chunk
        result1 = await self.add_lineage(
            from_entity_type="table",
            from_entity_fqn=artifact_fqn,
            to_entity_type="table",
            to_entity_fqn=chunk_fqn,
            description="Artifact 切分为 Chunk",
        )
        results.append(result1)

        # Chunk -> Evidence
        result2 = await self.add_lineage(
            from_entity_type="table",
            from_entity_fqn=chunk_fqn,
            to_entity_type="table",
            to_entity_fqn=evidence_fqn,
            description="Chunk 抽取 Evidence",
        )
        results.append(result2)

        return results

    async def get_lineage(
        self,
        entity_type: str,
        entity_fqn: str,
        upstream_depth: int = 3,
        downstream_depth: int = 3,
    ) -> dict[str, Any]:
        """获取实体的血缘关系。"""
        params = {
            "upstreamDepth": upstream_depth,
            "downstreamDepth": downstream_depth,
        }
        return await self._get(
            f"/lineage/{entity_type}/name/{entity_fqn}",
            params=params,
        )

    # ============ 标签管理 ============

    async def create_tag_category(
        self,
        name: str,
        description: str = "",
    ) -> dict[str, Any]:
        """创建标签分类。"""
        payload = {
            "name": name,
            "description": description,
            "categoryType": "Classification",
        }
        return await self._post("/classifications", payload)

    async def create_tag(
        self,
        classification_name: str,
        tag_name: str,
        description: str = "",
    ) -> dict[str, Any]:
        """创建标签。"""
        payload = {
            "name": tag_name,
            "description": description,
            "classification": classification_name,
        }
        return await self._post("/tags", payload)

    async def add_tag_to_entity(
        self,
        entity_type: str,
        entity_fqn: str,
        tag_fqn: str,
    ) -> dict[str, Any]:
        """给实体添加标签。"""
        payload = [
            {
                "op": "add",
                "path": "/tags/-",
                "value": {
                    "tagFQN": tag_fqn,
                    "source": "Classification",
                    "labelType": "Manual",
                    "state": "Confirmed",
                },
            }
        ]
        return await self._patch(f"/{entity_type}/name/{entity_fqn}", payload)

    async def list_tags(self, classification_name: str = "") -> list[dict[str, Any]]:
        """列出标签。"""
        params = {}
        if classification_name:
            params["classification"] = classification_name
        result = await self._get("/tags", params=params)
        return result.get("data", [])

    # ============ 责任人管理 ============

    async def set_owner(
        self,
        entity_type: str,
        entity_fqn: str,
        owner_name: str,
        owner_type: str = "user",
    ) -> dict[str, Any]:
        """设置实体责任人。"""
        payload = [
            {
                "op": "add",
                "path": "/owner",
                "value": {
                    "type": owner_type,
                    "name": owner_name,
                },
            }
        ]
        return await self._patch(f"/{entity_type}/name/{entity_fqn}", payload)

    # ============ 内部方法 ============

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """发送 GET 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._base_url}{path}"
        async with self._session.get(url, params=params) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"OpenMetadata API 错误: {resp.status} - {text}")
            return await resp.json()

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """发送 POST 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._base_url}{path}"
        async with self._session.post(url, json=payload) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"OpenMetadata API 错误: {resp.status} - {text}")
            return await resp.json()

    async def _put(
        self,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """发送 PUT 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._base_url}{path}"
        async with self._session.put(url, json=payload) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"OpenMetadata API 错误: {resp.status} - {text}")
            return await resp.json()

    async def _patch(
        self,
        path: str,
        payload: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """发送 PATCH 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._base_url}{path}"
        headers = {"Content-Type": "application/json-patch+json"}
        async with self._session.patch(url, json=payload, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"OpenMetadata API 错误: {resp.status} - {text}")
            return await resp.json()


def get_openmetadata_config_from_env() -> OpenMetadataConfig:
    """从环境变量获取 OpenMetadata 配置。"""
    import os

    return OpenMetadataConfig(
        server_url=os.getenv("OPENMETADATA_SERVER_URL", "http://localhost:8585/api"),
        api_version=os.getenv("OPENMETADATA_API_VERSION", "v1"),
        auth_token=os.getenv("OPENMETADATA_AUTH_TOKEN", ""),
        timeout=int(os.getenv("OPENMETADATA_TIMEOUT", "30")),
    )
