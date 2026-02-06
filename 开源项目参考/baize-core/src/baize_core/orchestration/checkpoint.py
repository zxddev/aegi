"""检查点机制。

实现 OODA/STORM 状态持久化与恢复，支持 Postgres + Redis 双后端。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field


class CheckpointMeta(BaseModel):
    """检查点元数据。"""

    checkpoint_id: str = Field(description="检查点唯一标识")
    thread_id: str = Field(description="线程/任务标识")
    step: str = Field(description="当前节点名称")
    created_at: datetime = Field(description="创建时间")


class Checkpoint(BaseModel):
    """检查点完整数据。"""

    checkpoint_id: str = Field(
        default_factory=lambda: f"ckpt_{uuid4().hex[:12]}",
        description="检查点唯一标识",
    )
    thread_id: str = Field(description="线程/任务标识")
    state: dict[str, Any] = Field(description="完整状态（OodaState / StormState）")
    step: str = Field(description="当前节点名称")
    parent_checkpoint_id: str | None = Field(
        default=None, description="父检查点标识（用于回滚）"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="创建时间",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外元数据")

    def to_meta(self) -> CheckpointMeta:
        """转换为元数据。"""
        return CheckpointMeta(
            checkpoint_id=self.checkpoint_id,
            thread_id=self.thread_id,
            step=self.step,
            created_at=self.created_at,
        )


@runtime_checkable
class CheckpointStore(Protocol):
    """检查点存储协议。"""

    async def save(self, checkpoint: Checkpoint) -> None:
        """保存检查点。"""
        ...

    async def load(self, thread_id: str) -> Checkpoint | None:
        """加载最新检查点。"""
        ...

    async def load_by_id(self, checkpoint_id: str) -> Checkpoint | None:
        """根据 ID 加载检查点。"""
        ...

    async def list_checkpoints(self, thread_id: str) -> list[CheckpointMeta]:
        """列出指定线程的所有检查点。"""
        ...

    async def delete(self, checkpoint_id: str) -> bool:
        """删除检查点。"""
        ...

    async def delete_thread(self, thread_id: str) -> int:
        """删除指定线程的所有检查点，返回删除数量。"""
        ...


class PostgresCheckpointStore:
    """PostgreSQL 检查点存储。

    使用 `checkpoints` 表存储检查点，支持 LangGraph 兼容的接口。
    """

    def __init__(self, connection_pool: Any) -> None:
        """初始化存储。

        Args:
            connection_pool: asyncpg 连接池
        """
        self._pool = connection_pool

    async def save(self, checkpoint: Checkpoint) -> None:
        """保存检查点。"""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO baize_core.checkpoints (
                    checkpoint_id, thread_id, state_json, step,
                    parent_checkpoint_id, created_at, checkpoint_meta
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (checkpoint_id) DO UPDATE SET
                    state_json = EXCLUDED.state_json,
                    step = EXCLUDED.step,
                    checkpoint_meta = EXCLUDED.checkpoint_meta
                """,
                checkpoint.checkpoint_id,
                checkpoint.thread_id,
                json.dumps(checkpoint.state, default=str, ensure_ascii=False),
                checkpoint.step,
                checkpoint.parent_checkpoint_id,
                checkpoint.created_at,
                json.dumps(checkpoint.metadata, default=str, ensure_ascii=False),
            )

    async def load(self, thread_id: str) -> Checkpoint | None:
        """加载指定线程的最新检查点。"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT checkpoint_id, thread_id, state_json, step,
                       parent_checkpoint_id, created_at, checkpoint_meta
                FROM baize_core.checkpoints
                WHERE thread_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                thread_id,
            )
            if row is None:
                return None
            return self._row_to_checkpoint(row)

    async def load_by_id(self, checkpoint_id: str) -> Checkpoint | None:
        """根据 ID 加载检查点。"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT checkpoint_id, thread_id, state_json, step,
                       parent_checkpoint_id, created_at, checkpoint_meta
                FROM baize_core.checkpoints
                WHERE checkpoint_id = $1
                """,
                checkpoint_id,
            )
            if row is None:
                return None
            return self._row_to_checkpoint(row)

    async def list_checkpoints(self, thread_id: str) -> list[CheckpointMeta]:
        """列出指定线程的所有检查点。"""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT checkpoint_id, thread_id, step, created_at
                FROM baize_core.checkpoints
                WHERE thread_id = $1
                ORDER BY created_at DESC
                """,
                thread_id,
            )
            return [
                CheckpointMeta(
                    checkpoint_id=row["checkpoint_id"],
                    thread_id=row["thread_id"],
                    step=row["step"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def delete(self, checkpoint_id: str) -> bool:
        """删除检查点。"""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM baize_core.checkpoints
                WHERE checkpoint_id = $1
                """,
                checkpoint_id,
            )
            return result == "DELETE 1"

    async def delete_thread(self, thread_id: str) -> int:
        """删除指定线程的所有检查点。"""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM baize_core.checkpoints
                WHERE thread_id = $1
                """,
                thread_id,
            )
            # result 格式类似 "DELETE 5"
            count_str = result.split()[-1] if result else "0"
            return int(count_str)

    def _row_to_checkpoint(self, row: Any) -> Checkpoint:
        """将数据库行转换为 Checkpoint。"""
        state_json = row["state_json"]
        metadata_json = row["checkpoint_meta"]
        return Checkpoint(
            checkpoint_id=row["checkpoint_id"],
            thread_id=row["thread_id"],
            state=json.loads(state_json) if isinstance(state_json, str) else state_json,
            step=row["step"],
            parent_checkpoint_id=row["parent_checkpoint_id"],
            created_at=row["created_at"],
            metadata=json.loads(metadata_json)
            if isinstance(metadata_json, str)
            else (metadata_json or {}),
        )


class RedisCheckpointStore:
    """Redis 检查点存储。

    使用 Redis HASH 存储状态，支持 TTL 配置。
    """

    # Redis 键前缀
    KEY_PREFIX = "checkpoint:"
    THREAD_INDEX_PREFIX = "checkpoint:thread:"

    def __init__(
        self,
        redis_client: Any,
        ttl_seconds: int = 86400 * 7,
    ) -> None:
        """初始化存储。

        Args:
            redis_client: aioredis 客户端
            ttl_seconds: 检查点过期时间（默认 7 天）
        """
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _checkpoint_key(self, checkpoint_id: str) -> str:
        """获取检查点键。"""
        return f"{self.KEY_PREFIX}{checkpoint_id}"

    def _thread_index_key(self, thread_id: str) -> str:
        """获取线程索引键。"""
        return f"{self.THREAD_INDEX_PREFIX}{thread_id}"

    async def save(self, checkpoint: Checkpoint) -> None:
        """保存检查点。"""
        key = self._checkpoint_key(checkpoint.checkpoint_id)
        data = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "thread_id": checkpoint.thread_id,
            "state": json.dumps(checkpoint.state, default=str, ensure_ascii=False),
            "step": checkpoint.step,
            "parent_checkpoint_id": checkpoint.parent_checkpoint_id or "",
            "created_at": checkpoint.created_at.isoformat(),
            "metadata": json.dumps(
                checkpoint.metadata, default=str, ensure_ascii=False
            ),
        }
        await self._redis.hset(key, mapping=data)
        await self._redis.expire(key, self._ttl)

        # 更新线程索引（有序集合，按时间戳排序）
        index_key = self._thread_index_key(checkpoint.thread_id)
        score = checkpoint.created_at.timestamp()
        await self._redis.zadd(index_key, {checkpoint.checkpoint_id: score})
        await self._redis.expire(index_key, self._ttl)

    async def load(self, thread_id: str) -> Checkpoint | None:
        """加载指定线程的最新检查点。"""
        index_key = self._thread_index_key(thread_id)
        # 获取最新的检查点 ID
        checkpoint_ids = await self._redis.zrevrange(index_key, 0, 0)
        if not checkpoint_ids:
            return None
        checkpoint_id = checkpoint_ids[0]
        if isinstance(checkpoint_id, bytes):
            checkpoint_id = checkpoint_id.decode("utf-8")
        return await self.load_by_id(checkpoint_id)

    async def load_by_id(self, checkpoint_id: str) -> Checkpoint | None:
        """根据 ID 加载检查点。"""
        key = self._checkpoint_key(checkpoint_id)
        data = await self._redis.hgetall(key)
        if not data:
            return None
        return self._data_to_checkpoint(data)

    async def list_checkpoints(self, thread_id: str) -> list[CheckpointMeta]:
        """列出指定线程的所有检查点。"""
        index_key = self._thread_index_key(thread_id)
        checkpoint_ids = await self._redis.zrevrange(index_key, 0, -1)
        result: list[CheckpointMeta] = []
        for checkpoint_id in checkpoint_ids:
            if isinstance(checkpoint_id, bytes):
                checkpoint_id = checkpoint_id.decode("utf-8")
            checkpoint = await self.load_by_id(checkpoint_id)
            if checkpoint:
                result.append(checkpoint.to_meta())
        return result

    async def delete(self, checkpoint_id: str) -> bool:
        """删除检查点。"""
        key = self._checkpoint_key(checkpoint_id)
        # 先获取 thread_id 以更新索引
        data = await self._redis.hgetall(key)
        if not data:
            return False
        thread_id = data.get(b"thread_id") or data.get("thread_id")
        if isinstance(thread_id, bytes):
            thread_id = thread_id.decode("utf-8")
        # 删除检查点
        deleted = await self._redis.delete(key)
        # 从索引中移除
        if thread_id:
            index_key = self._thread_index_key(thread_id)
            await self._redis.zrem(index_key, checkpoint_id)
        return deleted > 0

    async def delete_thread(self, thread_id: str) -> int:
        """删除指定线程的所有检查点。"""
        index_key = self._thread_index_key(thread_id)
        checkpoint_ids = await self._redis.zrange(index_key, 0, -1)
        count = 0
        for checkpoint_id in checkpoint_ids:
            if isinstance(checkpoint_id, bytes):
                checkpoint_id = checkpoint_id.decode("utf-8")
            key = self._checkpoint_key(checkpoint_id)
            deleted = await self._redis.delete(key)
            if deleted:
                count += 1
        # 删除索引
        await self._redis.delete(index_key)
        return count

    def _data_to_checkpoint(self, data: dict[Any, Any]) -> Checkpoint:
        """将 Redis 数据转换为 Checkpoint。"""

        # 处理 bytes 键
        def get_str(key: str) -> str:
            value = data.get(key.encode()) or data.get(key) or ""
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return str(value)

        state_str = get_str("state")
        metadata_str = get_str("metadata")
        parent_id = get_str("parent_checkpoint_id")

        return Checkpoint(
            checkpoint_id=get_str("checkpoint_id"),
            thread_id=get_str("thread_id"),
            state=json.loads(state_str) if state_str else {},
            step=get_str("step"),
            parent_checkpoint_id=parent_id if parent_id else None,
            created_at=datetime.fromisoformat(get_str("created_at")),
            metadata=json.loads(metadata_str) if metadata_str else {},
        )


@dataclass
class CheckpointManager:
    """检查点管理器。

    封装检查点操作，提供统一的保存/加载/恢复接口。
    """

    store: CheckpointStore
    auto_save: bool = True

    async def save_state(
        self,
        thread_id: str,
        state: dict[str, Any],
        step: str,
        parent_checkpoint_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Checkpoint:
        """保存状态到检查点。

        Args:
            thread_id: 线程/任务标识
            state: 完整状态
            step: 当前节点名称
            parent_checkpoint_id: 父检查点标识
            metadata: 额外元数据

        Returns:
            保存的检查点
        """
        checkpoint = Checkpoint(
            thread_id=thread_id,
            state=state,
            step=step,
            parent_checkpoint_id=parent_checkpoint_id,
            metadata=metadata or {},
        )
        await self.store.save(checkpoint)
        return checkpoint

    async def restore_state(self, thread_id: str) -> dict[str, Any] | None:
        """恢复最新状态。

        Args:
            thread_id: 线程/任务标识

        Returns:
            恢复的状态，如果没有检查点则返回 None
        """
        checkpoint = await self.store.load(thread_id)
        if checkpoint is None:
            return None
        return checkpoint.state

    async def restore_from_checkpoint(
        self, checkpoint_id: str
    ) -> tuple[dict[str, Any], str] | None:
        """从指定检查点恢复状态。

        Args:
            checkpoint_id: 检查点标识

        Returns:
            (状态, 节点名称) 元组，如果没有检查点则返回 None
        """
        checkpoint = await self.store.load_by_id(checkpoint_id)
        if checkpoint is None:
            return None
        return checkpoint.state, checkpoint.step

    async def list_history(self, thread_id: str) -> list[CheckpointMeta]:
        """列出检查点历史。

        Args:
            thread_id: 线程/任务标识

        Returns:
            检查点元数据列表，按时间倒序
        """
        return await self.store.list_checkpoints(thread_id)

    async def rollback_to(
        self, thread_id: str, checkpoint_id: str
    ) -> dict[str, Any] | None:
        """回滚到指定检查点。

        删除该检查点之后的所有检查点，返回恢复的状态。

        Args:
            thread_id: 线程/任务标识
            checkpoint_id: 目标检查点标识

        Returns:
            恢复的状态，如果检查点不存在则返回 None
        """
        target = await self.store.load_by_id(checkpoint_id)
        if target is None or target.thread_id != thread_id:
            return None

        # 获取所有检查点并删除目标之后的
        all_checkpoints = await self.store.list_checkpoints(thread_id)
        for meta in all_checkpoints:
            if meta.created_at > target.created_at:
                await self.store.delete(meta.checkpoint_id)

        return target.state

    async def cleanup(self, thread_id: str) -> int:
        """清理指定线程的所有检查点。

        Args:
            thread_id: 线程/任务标识

        Returns:
            删除的检查点数量
        """
        return await self.store.delete_thread(thread_id)
