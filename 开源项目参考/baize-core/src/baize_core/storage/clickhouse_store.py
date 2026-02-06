"""ClickHouse OLAP 存储。

提供以下能力：
- 审计日志聚合存储
- Token 使用量统计
- 工具调用成功率统计
- 趋势分析查询
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ClickHouseConfig:
    """ClickHouse 配置。"""

    host: str = "localhost"
    port: int = 8123  # HTTP 端口
    database: str = "baize_core"
    user: str = "default"
    password: str = ""
    secure: bool = False


@dataclass
class AuditLogEntry:
    """审计日志条目（用于 ClickHouse 存储）。"""

    trace_id: str
    event_type: str  # tool_call, model_call, policy_decision
    task_id: str
    timestamp: datetime
    duration_ms: int
    success: bool
    # 工具调用字段
    tool_name: str | None = None
    # 模型调用字段
    model: str | None = None
    stage: str | None = None
    token_count: int | None = None
    # 策略决策字段
    action: str | None = None
    allow: bool | None = None
    # 错误信息
    error_type: str | None = None
    error_message: str | None = None
    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsageStats:
    """Token 使用量统计。"""

    period_start: datetime
    period_end: datetime
    total_tokens: int
    model_breakdown: dict[str, int]
    stage_breakdown: dict[str, int]


@dataclass
class ToolCallStats:
    """工具调用统计。"""

    period_start: datetime
    period_end: datetime
    total_calls: int
    success_count: int
    failure_count: int
    success_rate: float
    tool_breakdown: dict[str, dict[str, int]]
    avg_duration_ms: float


class ClickHouseStore:
    """ClickHouse 存储客户端。"""

    def __init__(self, config: ClickHouseConfig) -> None:
        """初始化 ClickHouse 客户端。

        Args:
            config: ClickHouse 配置
        """
        self._config = config
        self._client: Any = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """是否已连接。"""
        return self._connected

    async def connect(self) -> None:
        """建立连接。"""
        if self._connected:
            return

        try:
            import clickhouse_connect

            self._client = clickhouse_connect.get_client(
                host=self._config.host,
                port=self._config.port,
                database=self._config.database,
                username=self._config.user,
                password=self._config.password,
                secure=self._config.secure,
            )
            self._connected = True
            logger.info("ClickHouse 连接成功: %s", self._config.host)

            # 确保表存在
            await self._ensure_tables()
        except ImportError:
            logger.warning("clickhouse-connect 未安装，使用模拟模式")
            self._connected = False
        except Exception as exc:
            logger.error("ClickHouse 连接失败: %s", exc)
            raise

    async def close(self) -> None:
        """关闭连接。"""
        if self._client:
            self._client.close()
            self._client = None
        self._connected = False
        logger.info("ClickHouse 连接已关闭")

    async def __aenter__(self) -> ClickHouseStore:
        """异步上下文管理器入口。"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口。"""
        await self.close()

    async def _ensure_tables(self) -> None:
        """确保必要的表存在。"""
        if not self._client:
            return

        # 审计日志表
        self._client.command("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                trace_id String,
                event_type LowCardinality(String),
                task_id String,
                timestamp DateTime64(3),
                duration_ms UInt32,
                success UInt8,
                tool_name Nullable(String),
                model Nullable(String),
                stage Nullable(LowCardinality(String)),
                token_count Nullable(UInt32),
                action Nullable(LowCardinality(String)),
                allow Nullable(UInt8),
                error_type Nullable(String),
                error_message Nullable(String),
                metadata String DEFAULT '{}'
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (timestamp, trace_id)
            TTL timestamp + INTERVAL 90 DAY
        """)

        # Token 使用量汇总表
        self._client.command("""
            CREATE TABLE IF NOT EXISTS token_usage_daily (
                date Date,
                model LowCardinality(String),
                stage LowCardinality(String),
                total_tokens UInt64,
                call_count UInt32
            ) ENGINE = SummingMergeTree()
            PARTITION BY toYYYYMM(date)
            ORDER BY (date, model, stage)
        """)

        # 工具调用统计表
        self._client.command("""
            CREATE TABLE IF NOT EXISTS tool_calls_daily (
                date Date,
                tool_name LowCardinality(String),
                success_count UInt32,
                failure_count UInt32,
                total_duration_ms UInt64
            ) ENGINE = SummingMergeTree()
            PARTITION BY toYYYYMM(date)
            ORDER BY (date, tool_name)
        """)

        logger.info("ClickHouse 表已创建/验证")

    # ============ 写入方法 ============

    async def insert_audit_log(self, entry: AuditLogEntry) -> None:
        """插入审计日志。"""
        if not self._client:
            logger.debug("ClickHouse 未连接，跳过插入")
            return

        import json

        self._client.insert(
            "audit_logs",
            [
                [
                    entry.trace_id,
                    entry.event_type,
                    entry.task_id,
                    entry.timestamp,
                    entry.duration_ms,
                    1 if entry.success else 0,
                    entry.tool_name,
                    entry.model,
                    entry.stage,
                    entry.token_count,
                    entry.action,
                    1 if entry.allow else 0 if entry.allow is not None else None,
                    entry.error_type,
                    entry.error_message,
                    json.dumps(entry.metadata, ensure_ascii=False),
                ]
            ],
            column_names=[
                "trace_id",
                "event_type",
                "task_id",
                "timestamp",
                "duration_ms",
                "success",
                "tool_name",
                "model",
                "stage",
                "token_count",
                "action",
                "allow",
                "error_type",
                "error_message",
                "metadata",
            ],
        )

    async def insert_audit_logs_batch(self, entries: list[AuditLogEntry]) -> None:
        """批量插入审计日志。"""
        if not self._client or not entries:
            return

        import json

        data = [
            [
                e.trace_id,
                e.event_type,
                e.task_id,
                e.timestamp,
                e.duration_ms,
                1 if e.success else 0,
                e.tool_name,
                e.model,
                e.stage,
                e.token_count,
                e.action,
                1 if e.allow else 0 if e.allow is not None else None,
                e.error_type,
                e.error_message,
                json.dumps(e.metadata, ensure_ascii=False),
            ]
            for e in entries
        ]

        self._client.insert(
            "audit_logs",
            data,
            column_names=[
                "trace_id",
                "event_type",
                "task_id",
                "timestamp",
                "duration_ms",
                "success",
                "tool_name",
                "model",
                "stage",
                "token_count",
                "action",
                "allow",
                "error_type",
                "error_message",
                "metadata",
            ],
        )
        logger.debug("批量插入审计日志: %d 条", len(entries))

    # ============ 查询方法 ============

    async def get_token_usage_stats(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> TokenUsageStats:
        """获取 Token 使用量统计。"""
        if not self._client:
            return TokenUsageStats(
                period_start=start_time,
                period_end=end_time,
                total_tokens=0,
                model_breakdown={},
                stage_breakdown={},
            )

        # 总量
        total_result = self._client.query(
            """
            SELECT sum(token_count) as total
            FROM audit_logs
            WHERE event_type = 'model_call'
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
              AND success = 1
            """,
            parameters={"start": start_time, "end": end_time},
        )
        total_tokens = total_result.result_rows[0][0] or 0

        # 按模型分组
        model_result = self._client.query(
            """
            SELECT model, sum(token_count) as tokens
            FROM audit_logs
            WHERE event_type = 'model_call'
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
              AND success = 1
            GROUP BY model
            """,
            parameters={"start": start_time, "end": end_time},
        )
        model_breakdown = {row[0]: row[1] for row in model_result.result_rows if row[0]}

        # 按阶段分组
        stage_result = self._client.query(
            """
            SELECT stage, sum(token_count) as tokens
            FROM audit_logs
            WHERE event_type = 'model_call'
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
              AND success = 1
            GROUP BY stage
            """,
            parameters={"start": start_time, "end": end_time},
        )
        stage_breakdown = {row[0]: row[1] for row in stage_result.result_rows if row[0]}

        return TokenUsageStats(
            period_start=start_time,
            period_end=end_time,
            total_tokens=total_tokens,
            model_breakdown=model_breakdown,
            stage_breakdown=stage_breakdown,
        )

    async def get_tool_call_stats(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> ToolCallStats:
        """获取工具调用统计。"""
        if not self._client:
            return ToolCallStats(
                period_start=start_time,
                period_end=end_time,
                total_calls=0,
                success_count=0,
                failure_count=0,
                success_rate=0.0,
                tool_breakdown={},
                avg_duration_ms=0.0,
            )

        # 总体统计
        overall_result = self._client.query(
            """
            SELECT
                count() as total,
                sum(success) as success_count,
                avg(duration_ms) as avg_duration
            FROM audit_logs
            WHERE event_type = 'tool_call'
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
            """,
            parameters={"start": start_time, "end": end_time},
        )
        row = overall_result.result_rows[0]
        total_calls = row[0] or 0
        success_count = row[1] or 0
        avg_duration = row[2] or 0.0
        failure_count = total_calls - success_count

        # 按工具分组
        tool_result = self._client.query(
            """
            SELECT
                tool_name,
                count() as total,
                sum(success) as success_count
            FROM audit_logs
            WHERE event_type = 'tool_call'
              AND timestamp >= %(start)s
              AND timestamp < %(end)s
            GROUP BY tool_name
            """,
            parameters={"start": start_time, "end": end_time},
        )
        tool_breakdown = {
            row[0]: {"total": row[1], "success": row[2], "failure": row[1] - row[2]}
            for row in tool_result.result_rows
            if row[0]
        }

        success_rate = success_count / max(total_calls, 1)

        return ToolCallStats(
            period_start=start_time,
            period_end=end_time,
            total_calls=total_calls,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=success_rate,
            tool_breakdown=tool_breakdown,
            avg_duration_ms=avg_duration,
        )

    async def get_daily_trends(
        self,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """获取每日趋势数据。"""
        if not self._client:
            return []

        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=days)

        result = self._client.query(
            """
            SELECT
                toDate(timestamp) as date,
                event_type,
                count() as total,
                sum(success) as success_count,
                sum(token_count) as tokens,
                avg(duration_ms) as avg_duration
            FROM audit_logs
            WHERE timestamp >= %(start)s
              AND timestamp < %(end)s
            GROUP BY date, event_type
            ORDER BY date
            """,
            parameters={"start": start_time, "end": end_time},
        )

        return [
            {
                "date": row[0].isoformat() if row[0] else None,
                "event_type": row[1],
                "total": row[2],
                "success_count": row[3],
                "tokens": row[4],
                "avg_duration_ms": row[5],
            }
            for row in result.result_rows
        ]

    async def get_error_summary(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """获取错误摘要。"""
        if not self._client:
            return []

        result = self._client.query(
            """
            SELECT
                error_type,
                count() as count,
                any(error_message) as sample_message
            FROM audit_logs
            WHERE timestamp >= %(start)s
              AND timestamp < %(end)s
              AND success = 0
              AND error_type IS NOT NULL
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT %(limit)s
            """,
            parameters={"start": start_time, "end": end_time, "limit": limit},
        )

        return [
            {
                "error_type": row[0],
                "count": row[1],
                "sample_message": row[2],
            }
            for row in result.result_rows
        ]


def get_clickhouse_config_from_env() -> ClickHouseConfig:
    """从环境变量获取 ClickHouse 配置。"""
    import os

    return ClickHouseConfig(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        database=os.getenv("CLICKHOUSE_DATABASE", "baize_core"),
        user=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        secure=os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true",
    )
