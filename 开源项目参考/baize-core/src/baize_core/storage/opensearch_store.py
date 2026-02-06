"""OpenSearch 全文检索存储模块。

提供以下功能：
- 文档块（Chunk）的全文索引与搜索
- 审计事件的索引与查询
- 索引生命周期管理
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from baize_core.config.settings import OpenSearchConfig

logger = logging.getLogger(__name__)

# 尝试导入 opensearchpy，如果未安装则提供 stub
try:
    from opensearchpy import AsyncOpenSearch, NotFoundError
except ImportError:
    AsyncOpenSearch = None
    NotFoundError = Exception


# Chunk 索引映射
CHUNK_INDEX_MAPPING: dict[str, Any] = {
    "mappings": {
        "properties": {
            "chunk_uid": {"type": "keyword"},
            "artifact_uid": {"type": "keyword"},
            "task_id": {"type": "keyword"},
            "text": {"type": "text", "analyzer": "standard"},
            "text_sha256": {"type": "keyword"},
            "anchor": {
                "type": "object",
                "properties": {
                    "type": {"type": "keyword"},
                    "ref": {"type": "keyword"},
                },
            },
            "created_at": {"type": "date"},
            "metadata": {"type": "object", "enabled": False},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "default": {
                    "type": "standard",
                }
            }
        },
    },
}

# 审计事件索引映射
AUDIT_INDEX_MAPPING: dict[str, Any] = {
    "mappings": {
        "properties": {
            "event_id": {"type": "keyword"},
            "event_type": {"type": "keyword"},
            "task_id": {"type": "keyword"},
            "trace_id": {"type": "keyword"},
            "timestamp": {"type": "date"},
            "tool_name": {"type": "keyword"},
            "model_name": {"type": "keyword"},
            "success": {"type": "boolean"},
            "duration_ms": {"type": "integer"},
            "error_type": {"type": "keyword"},
            "error_message": {"type": "text"},
            "input_ref": {"type": "keyword"},
            "output_ref": {"type": "keyword"},
            "metadata": {"type": "object", "enabled": False},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
}


@dataclass
class ChunkSearchResult:
    """Chunk 搜索结果。"""

    chunk_uid: str
    artifact_uid: str
    text: str
    score: float
    highlights: list[str]


@dataclass
class AuditSearchResult:
    """审计事件搜索结果。"""

    event_id: str
    event_type: str
    task_id: str | None
    trace_id: str | None
    timestamp: datetime
    tool_name: str | None
    model_name: str | None
    success: bool
    duration_ms: int | None
    error_type: str | None
    error_message: str | None


class OpenSearchStore:
    """OpenSearch 存储管理器。"""

    def __init__(self, config: OpenSearchConfig) -> None:
        """初始化 OpenSearch 客户端。

        Args:
            config: OpenSearch 配置
        """
        if AsyncOpenSearch is None:
            raise ImportError("opensearchpy 未安装。请运行: pip install opensearch-py")
        self._config = config
        self._client: AsyncOpenSearch | None = None

    async def connect(self) -> None:
        """建立连接。"""
        if self._client is not None:
            return
        auth = (self._config.http_auth_user, self._config.http_auth_password)
        self._client = AsyncOpenSearch(
            hosts=[{"host": self._config.host, "port": self._config.port}],
            http_auth=auth,
            use_ssl=self._config.use_ssl,
            verify_certs=self._config.verify_certs,
            ssl_show_warn=False,
        )
        logger.info(
            "OpenSearch 连接已建立: %s:%d", self._config.host, self._config.port
        )

    async def close(self) -> None:
        """关闭连接。"""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("OpenSearch 连接已关闭")

    def _ensure_connected(self) -> AsyncOpenSearch:
        """确保已连接。"""
        if self._client is None:
            raise RuntimeError("OpenSearch 未连接，请先调用 connect()")
        return self._client

    # ========== 索引管理 ==========

    async def create_chunk_index(self) -> None:
        """创建 Chunk 索引。"""
        client = self._ensure_connected()
        index_name = self._config.chunk_index
        exists = await client.indices.exists(index=index_name)
        if not exists:
            await client.indices.create(index=index_name, body=CHUNK_INDEX_MAPPING)
            logger.info("创建 Chunk 索引: %s", index_name)

    async def create_audit_index(self) -> None:
        """创建审计事件索引。"""
        client = self._ensure_connected()
        index_name = self._config.audit_index
        exists = await client.indices.exists(index=index_name)
        if not exists:
            await client.indices.create(index=index_name, body=AUDIT_INDEX_MAPPING)
            logger.info("创建审计索引: %s", index_name)

    async def delete_index(self, index_name: str) -> None:
        """删除索引。"""
        client = self._ensure_connected()
        try:
            await client.indices.delete(index=index_name)
            logger.info("删除索引: %s", index_name)
        except NotFoundError:
            logger.debug("索引不存在，跳过删除: %s", index_name)

    async def refresh_index(self, index_name: str) -> None:
        """刷新索引。"""
        client = self._ensure_connected()
        await client.indices.refresh(index=index_name)

    async def get_index_stats(self, index_name: str) -> dict[str, Any]:
        """获取索引统计信息。"""
        client = self._ensure_connected()
        try:
            stats = await client.indices.stats(index=index_name)
            return dict(stats)
        except NotFoundError:
            return {"error": "索引不存在"}

    # ========== Chunk 操作 ==========

    async def index_chunk(
        self,
        chunk_uid: str,
        artifact_uid: str,
        text: str,
        text_sha256: str,
        anchor: dict[str, str],
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """索引单个 Chunk。"""
        client = self._ensure_connected()
        doc = {
            "chunk_uid": chunk_uid,
            "artifact_uid": artifact_uid,
            "task_id": task_id,
            "text": text,
            "text_sha256": text_sha256,
            "anchor": anchor,
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
        }
        await client.index(
            index=self._config.chunk_index,
            id=chunk_uid,
            body=doc,
        )

    async def index_chunks_bulk(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """批量索引 Chunk。

        Args:
            chunks: Chunk 列表，每个包含 chunk_uid, artifact_uid, text, text_sha256, anchor

        Returns:
            成功索引的数量
        """
        if not chunks:
            return 0
        client = self._ensure_connected()
        actions: list[dict[str, Any]] = []
        for chunk in chunks:
            action = {
                "index": {"_index": self._config.chunk_index, "_id": chunk["chunk_uid"]}
            }
            doc = {
                "chunk_uid": chunk["chunk_uid"],
                "artifact_uid": chunk["artifact_uid"],
                "task_id": chunk.get("task_id"),
                "text": chunk["text"],
                "text_sha256": chunk["text_sha256"],
                "anchor": chunk["anchor"],
                "created_at": datetime.now(UTC).isoformat(),
                "metadata": chunk.get("metadata", {}),
            }
            actions.append(action)
            actions.append(doc)
        response = await client.bulk(body=actions)
        errors = response.get("errors", False)
        if errors:
            error_count = sum(
                1
                for item in response.get("items", [])
                if "error" in item.get("index", {})
            )
            logger.warning("批量索引有 %d 个错误", error_count)
            return len(chunks) - error_count
        return len(chunks)

    async def search_chunks(
        self,
        query: str,
        max_results: int = 10,
        artifact_uid: str | None = None,
        task_id: str | None = None,
    ) -> list[ChunkSearchResult]:
        """全文搜索 Chunk。

        Args:
            query: 搜索查询
            max_results: 最大结果数
            artifact_uid: 可选，限定 artifact
            task_id: 可选，限定 task

        Returns:
            搜索结果列表
        """
        client = self._ensure_connected()
        must_clauses: list[dict[str, Any]] = [
            {"match": {"text": query}},
        ]
        if artifact_uid:
            must_clauses.append({"term": {"artifact_uid": artifact_uid}})
        if task_id:
            must_clauses.append({"term": {"task_id": task_id}})

        body = {
            "query": {"bool": {"must": must_clauses}},
            "size": max_results,
            "highlight": {
                "fields": {"text": {}},
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"],
            },
        }
        response = await client.search(index=self._config.chunk_index, body=body)
        results: list[ChunkSearchResult] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit["_source"]
            highlights = hit.get("highlight", {}).get("text", [])
            results.append(
                ChunkSearchResult(
                    chunk_uid=source["chunk_uid"],
                    artifact_uid=source["artifact_uid"],
                    text=source["text"],
                    score=hit["_score"],
                    highlights=highlights,
                )
            )
        return results

    async def delete_chunk(self, chunk_uid: str) -> bool:
        """删除 Chunk。"""
        client = self._ensure_connected()
        try:
            await client.delete(index=self._config.chunk_index, id=chunk_uid)
            return True
        except NotFoundError:
            return False

    async def delete_chunks_by_artifact(self, artifact_uid: str) -> int:
        """删除指定 artifact 的所有 Chunk。"""
        client = self._ensure_connected()
        body = {"query": {"term": {"artifact_uid": artifact_uid}}}
        response = await client.delete_by_query(
            index=self._config.chunk_index, body=body
        )
        return response.get("deleted", 0)

    # ========== 审计事件操作 ==========

    async def index_audit_event(
        self,
        event_id: str,
        event_type: str,
        timestamp: datetime,
        task_id: str | None = None,
        trace_id: str | None = None,
        tool_name: str | None = None,
        model_name: str | None = None,
        success: bool = True,
        duration_ms: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        input_ref: str | None = None,
        output_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """索引审计事件。"""
        client = self._ensure_connected()
        doc = {
            "event_id": event_id,
            "event_type": event_type,
            "task_id": task_id,
            "trace_id": trace_id,
            "timestamp": timestamp.isoformat(),
            "tool_name": tool_name,
            "model_name": model_name,
            "success": success,
            "duration_ms": duration_ms,
            "error_type": error_type,
            "error_message": error_message,
            "input_ref": input_ref,
            "output_ref": output_ref,
            "metadata": metadata or {},
        }
        await client.index(
            index=self._config.audit_index,
            id=event_id,
            body=doc,
        )

    async def search_audit_events(
        self,
        event_type: str | None = None,
        task_id: str | None = None,
        tool_name: str | None = None,
        model_name: str | None = None,
        success: bool | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_results: int = 100,
    ) -> list[AuditSearchResult]:
        """搜索审计事件。"""
        client = self._ensure_connected()
        must_clauses: list[dict[str, Any]] = []
        if event_type:
            must_clauses.append({"term": {"event_type": event_type}})
        if task_id:
            must_clauses.append({"term": {"task_id": task_id}})
        if tool_name:
            must_clauses.append({"term": {"tool_name": tool_name}})
        if model_name:
            must_clauses.append({"term": {"model_name": model_name}})
        if success is not None:
            must_clauses.append({"term": {"success": success}})
        if start_time or end_time:
            range_query: dict[str, Any] = {}
            if start_time:
                range_query["gte"] = start_time.isoformat()
            if end_time:
                range_query["lte"] = end_time.isoformat()
            must_clauses.append({"range": {"timestamp": range_query}})

        body: dict[str, Any] = {
            "size": max_results,
            "sort": [{"timestamp": {"order": "desc"}}],
        }
        if must_clauses:
            body["query"] = {"bool": {"must": must_clauses}}
        else:
            body["query"] = {"match_all": {}}

        response = await client.search(index=self._config.audit_index, body=body)
        results: list[AuditSearchResult] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit["_source"]
            results.append(
                AuditSearchResult(
                    event_id=source["event_id"],
                    event_type=source["event_type"],
                    task_id=source.get("task_id"),
                    trace_id=source.get("trace_id"),
                    timestamp=datetime.fromisoformat(
                        source["timestamp"].replace("Z", "+00:00")
                    ),
                    tool_name=source.get("tool_name"),
                    model_name=source.get("model_name"),
                    success=source.get("success", True),
                    duration_ms=source.get("duration_ms"),
                    error_type=source.get("error_type"),
                    error_message=source.get("error_message"),
                )
            )
        return results

    async def get_audit_stats(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """获取审计统计信息。"""
        client = self._ensure_connected()
        filter_clauses: list[dict[str, Any]] = []
        if start_time or end_time:
            range_query: dict[str, Any] = {}
            if start_time:
                range_query["gte"] = start_time.isoformat()
            if end_time:
                range_query["lte"] = end_time.isoformat()
            filter_clauses.append({"range": {"timestamp": range_query}})

        body: dict[str, Any] = {
            "size": 0,
            "aggs": {
                "by_event_type": {"terms": {"field": "event_type", "size": 50}},
                "by_tool": {"terms": {"field": "tool_name", "size": 50}},
                "by_model": {"terms": {"field": "model_name", "size": 50}},
                "success_rate": {"avg": {"field": "success"}},
                "avg_duration": {"avg": {"field": "duration_ms"}},
            },
        }
        if filter_clauses:
            body["query"] = {"bool": {"filter": filter_clauses}}

        response = await client.search(index=self._config.audit_index, body=body)
        aggs = response.get("aggregations", {})
        return {
            "total_events": response.get("hits", {}).get("total", {}).get("value", 0),
            "by_event_type": [
                {"type": bucket["key"], "count": bucket["doc_count"]}
                for bucket in aggs.get("by_event_type", {}).get("buckets", [])
            ],
            "by_tool": [
                {"tool": bucket["key"], "count": bucket["doc_count"]}
                for bucket in aggs.get("by_tool", {}).get("buckets", [])
            ],
            "by_model": [
                {"model": bucket["key"], "count": bucket["doc_count"]}
                for bucket in aggs.get("by_model", {}).get("buckets", [])
            ],
            "success_rate": aggs.get("success_rate", {}).get("value"),
            "avg_duration_ms": aggs.get("avg_duration", {}).get("value"),
        }
