"""Scrape Guard 数据源。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg
from asyncpg import exceptions as asyncpg_exceptions


@dataclass(frozen=True)
class ScrapeGuardSettings:
    """外联治理阈值。"""

    domain_rps: float
    domain_concurrency: int
    cache_ttl_seconds: int
    robots_require_allow: bool


@dataclass(frozen=True)
class ScrapeGuardSnapshot:
    """外联治理快照。"""

    allowed_domains: tuple[str, ...]
    denied_domains: tuple[str, ...]
    settings: ScrapeGuardSettings


def _normalize_dsn(dsn: str) -> str:
    """将 SQLAlchemy 风格的 DSN 转换为 asyncpg 兼容格式。"""
    # asyncpg 需要 postgresql:// 而不是 postgresql+asyncpg://
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    return dsn


class ScrapeGuardStore:
    """外联治理数据访问。"""

    def __init__(self, dsn: str) -> None:
        self._dsn = _normalize_dsn(dsn)
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """建立连接池。"""

        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(dsn=self._dsn)

    async def close(self) -> None:
        """关闭连接池。"""

        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None

    async def load_snapshot(self) -> ScrapeGuardSnapshot:
        """读取最新治理配置。"""

        if self._pool is None:
            raise RuntimeError("Scrape Guard 数据源未连接")
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT domain, policy
                FROM baize_core.scrape_guard_domains
                ORDER BY domain
                """
            )
            allowed: list[str] = []
            denied: list[str] = []
            for row in rows:
                domain = str(row["domain"]).strip().lower()
                policy = str(row["policy"]).strip().lower()
                if policy == "allow":
                    allowed.append(domain)
                elif policy == "deny":
                    denied.append(domain)
            settings_row = await connection.fetchrow(
                """
                SELECT domain_rps, domain_concurrency, cache_ttl_seconds, robots_require_allow
                FROM baize_core.scrape_guard_settings
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            if settings_row is None:
                raise RuntimeError("Scrape Guard 阈值配置缺失")
            settings = ScrapeGuardSettings(
                domain_rps=float(settings_row["domain_rps"]),
                domain_concurrency=int(settings_row["domain_concurrency"]),
                cache_ttl_seconds=int(settings_row["cache_ttl_seconds"]),
                robots_require_allow=bool(settings_row["robots_require_allow"]),
            )
        return ScrapeGuardSnapshot(
            allowed_domains=tuple(allowed),
            denied_domains=tuple(denied),
            settings=settings,
        )

    async def get_artifact(self, artifact_uid: str) -> tuple[str, str]:
        """读取 Artifact 存储信息。"""

        if self._pool is None:
            raise RuntimeError("Scrape Guard 数据源未连接")
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT storage_ref, mime_type
                FROM baize_core.artifacts
                WHERE artifact_uid = $1
                """,
                artifact_uid,
            )
            if row is None:
                raise RuntimeError("Artifact 不存在")
            return str(row["storage_ref"]), str(row["mime_type"])

    async def record_tool_trace(
        self,
        *,
        trace_id: str,
        tool_name: str,
        started_at: datetime,
        duration_ms: int,
        success: bool,
        error_type: str | None,
        error_message: str | None,
        result_ref: str | None,
        policy_decision_id: str | None,
        caller_trace_id: str | None,
        caller_policy_decision_id: str | None,
    ) -> None:
        """写入工具调用审计（使用 upsert 避免双写冲突）。"""

        if self._pool is None:
            raise RuntimeError("Scrape Guard 数据源未连接")
        async with self._pool.acquire() as connection:
            try:
                await connection.execute(
                    """
                    INSERT INTO baize_core.tool_traces (
                        trace_id,
                        tool_name,
                        started_at,
                        duration_ms,
                        success,
                        error_type,
                        error_message,
                        result_ref,
                        policy_decision_id,
                        caller_trace_id,
                        caller_policy_decision_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (trace_id) DO NOTHING
                    """,
                    trace_id,
                    tool_name,
                    started_at,
                    duration_ms,
                    success,
                    error_type,
                    error_message,
                    result_ref,
                    policy_decision_id,
                    caller_trace_id,
                    caller_policy_decision_id,
                )
            except asyncpg_exceptions.UndefinedColumnError:
                await connection.execute(
                    """
                    INSERT INTO baize_core.tool_traces (
                        trace_id,
                        tool_name,
                        started_at,
                        duration_ms,
                        success,
                        error_type,
                        error_message,
                        result_ref,
                        policy_decision_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (trace_id) DO NOTHING
                    """,
                    trace_id,
                    tool_name,
                    started_at,
                    duration_ms,
                    success,
                    error_type,
                    error_message,
                    result_ref,
                    policy_decision_id,
                )

    async def get_tool_trace(self, trace_id: str) -> dict[str, object] | None:
        """读取单个工具调用审计记录。"""

        if self._pool is None:
            raise RuntimeError("Scrape Guard 数据源未连接")
        async with self._pool.acquire() as connection:
            try:
                row = await connection.fetchrow(
                    """
                    SELECT trace_id,
                           tool_name,
                           started_at,
                           duration_ms,
                           success,
                           error_type,
                           error_message,
                           result_ref,
                           policy_decision_id,
                           caller_trace_id,
                           caller_policy_decision_id
                    FROM baize_core.tool_traces
                    WHERE trace_id = $1
                    """,
                    trace_id,
                )
            except asyncpg_exceptions.UndefinedColumnError:
                row = await connection.fetchrow(
                    """
                    SELECT trace_id,
                           tool_name,
                           started_at,
                           duration_ms,
                           success,
                           error_type,
                           error_message,
                           result_ref,
                           policy_decision_id
                    FROM baize_core.tool_traces
                    WHERE trace_id = $1
                    """,
                    trace_id,
                )
            if row is None:
                return None
            return _tool_trace_row_to_dict(row)

    async def query_tool_traces_by_decision(
        self, decision_id: str
    ) -> list[dict[str, object]]:
        """按策略决策 ID 查询工具调用审计。"""

        if self._pool is None:
            raise RuntimeError("Scrape Guard 数据源未连接")
        async with self._pool.acquire() as connection:
            try:
                rows = await connection.fetch(
                    """
                    SELECT trace_id,
                           tool_name,
                           started_at,
                           duration_ms,
                           success,
                           error_type,
                           error_message,
                           result_ref,
                           policy_decision_id,
                           caller_trace_id,
                           caller_policy_decision_id
                    FROM baize_core.tool_traces
                    WHERE policy_decision_id = $1
                       OR caller_policy_decision_id = $1
                    ORDER BY started_at DESC
                    """,
                    decision_id,
                )
            except asyncpg_exceptions.UndefinedColumnError:
                rows = await connection.fetch(
                    """
                    SELECT trace_id,
                           tool_name,
                           started_at,
                           duration_ms,
                           success,
                           error_type,
                           error_message,
                           result_ref,
                           policy_decision_id
                    FROM baize_core.tool_traces
                    WHERE policy_decision_id = $1
                    ORDER BY started_at DESC
                    """,
                    decision_id,
                )
            return [_tool_trace_row_to_dict(row) for row in rows]

    async def record_robots_check(
        self,
        *,
        tool_name: str,
        url: str,
        host: str,
        robots_url: str,
        allowed: bool,
        error_message: str | None,
        checked_at: datetime,
    ) -> None:
        """写入 robots.txt 审计记录。"""

        if self._pool is None:
            raise RuntimeError("Scrape Guard 数据源未连接")
        async with self._pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO baize_core.scrape_guard_robots_checks (
                    tool_name,
                    url,
                    host,
                    robots_url,
                    allowed,
                    error_message,
                    checked_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                tool_name,
                url,
                host,
                robots_url,
                allowed,
                error_message,
                checked_at,
            )

    async def record_tos_check(
        self,
        *,
        tool_name: str,
        url: str,
        host: str,
        tos_url: str | None,
        tos_found: bool,
        scraping_allowed: bool | None,
        tos_summary: str | None,
        error_message: str | None,
        checked_at: datetime,
    ) -> None:
        """写入 ToS（服务条款）审计记录。"""
        if self._pool is None:
            raise RuntimeError("Scrape Guard 数据源未连接")
        async with self._pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO baize_core.scrape_guard_tos_checks (
                    tool_name,
                    url,
                    host,
                    tos_url,
                    tos_found,
                    scraping_allowed,
                    tos_summary,
                    error_message,
                    checked_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                tool_name,
                url,
                host,
                tos_url,
                tos_found,
                scraping_allowed,
                tos_summary,
                error_message,
                checked_at,
            )


def _tool_trace_row_to_dict(row: asyncpg.Record) -> dict[str, object]:
    """转换 tool_traces 记录为字典。"""

    started_at = row.get("started_at")
    started_at_str = (
        started_at.isoformat().replace("+00:00", "Z")
        if isinstance(started_at, datetime)
        else None
    )
    return {
        "trace_id": row.get("trace_id"),
        "tool_name": row.get("tool_name"),
        "started_at": started_at_str,
        "duration_ms": row.get("duration_ms"),
        "success": row.get("success"),
        "error_type": row.get("error_type"),
        "error_message": row.get("error_message"),
        "result_ref": row.get("result_ref"),
        "policy_decision_id": row.get("policy_decision_id"),
        "caller_trace_id": row.get("caller_trace_id"),
        "caller_policy_decision_id": row.get("caller_policy_decision_id"),
    }

    async def get_tos_cache(self, host: str) -> dict[str, object] | None:
        """读取 ToS 缓存。"""
        if self._pool is None:
            raise RuntimeError("Scrape Guard 数据源未连接")
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT tos_url, tos_found, scraping_allowed, tos_summary, checked_at
                FROM baize_core.scrape_guard_tos_checks
                WHERE host = $1
                ORDER BY checked_at DESC
                LIMIT 1
                """,
                host,
            )
            if row is None:
                return None
            return {
                "tos_url": row["tos_url"],
                "tos_found": row["tos_found"],
                "scraping_allowed": row["scraping_allowed"],
                "tos_summary": row["tos_summary"],
                "checked_at": row["checked_at"],
            }
