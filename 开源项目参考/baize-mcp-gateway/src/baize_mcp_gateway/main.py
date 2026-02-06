"""MCP Gateway 入口。"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import subprocess
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from minio import Minio

from baize_mcp_gateway.config import GatewayConfig
from baize_mcp_gateway.db import ScrapeGuardStore
from baize_mcp_gateway.proxy_pool import (
    ProxyConfig,
    ProxyPool,
    ProxyPoolConfig,
    parse_proxy_list,
)
from baize_mcp_gateway.rate_limiter import (
    LimitDimension,
    MultiDimensionRateLimiter,
    RateLimitConfig,
    RateLimiter,
)
from baize_mcp_gateway.registry import (
    LoadedRegistry,
    RegistryReloader,
    ToolConfig,
    load_registry,
)
from baize_mcp_gateway.retry import (
    RetryConfig,
    create_audit_record,
    retry_async,
)
from baize_mcp_gateway.scrape_guard import ScrapeGuard
from baize_mcp_gateway.trace_context import parse_trace_context

logger = logging.getLogger(__name__)


@dataclass
class GatewayState:
    """网关运行时状态。"""

    config: GatewayConfig
    registry: LoadedRegistry
    tool_rate_limiters: dict[str, RateLimiter]
    registry_reloader: RegistryReloader | None
    scrape_guard: ScrapeGuard
    guard_store: ScrapeGuardStore | None
    minio_client: Minio
    proxy_pool: ProxyPool | None
    retry_config: RetryConfig | None
    rate_limiter: MultiDimensionRateLimiter | None


def _build_tool_rate_limiters(
    reg: LoadedRegistry,
) -> dict[str, RateLimiter]:
    """初始化/更新工具级限流器。"""
    new_limiters: dict[str, RateLimiter] = {}
    for tool_name, tool_config in reg.tools.items():
        if tool_config.rate_limit is not None:
            new_limiters[tool_name] = RateLimiter(
                RateLimitConfig(
                    requests_per_second=tool_config.rate_limit.requests_per_second,
                    burst_size=tool_config.rate_limit.burst_size,
                    dimension=LimitDimension.API_KEY,
                )
            )
            logger.info(
                "工具 %s 限流器已初始化: RPS=%.1f, Burst=%d",
                tool_name,
                tool_config.rate_limit.requests_per_second,
                tool_config.rate_limit.burst_size,
            )
    return new_limiters


def _update_tool_rate_limiters(state: GatewayState, reg: LoadedRegistry) -> None:
    """更新工具级限流器。"""
    state.tool_rate_limiters = _build_tool_rate_limiters(reg)


def _build_proxy_pool(config: GatewayConfig) -> ProxyPool | None:
    """初始化代理池。"""
    if not (config.proxy_enabled and config.proxy_list):
        return None
    pool_config = ProxyPoolConfig(
        health_check_interval_seconds=config.proxy_health_check_interval,
        health_check_timeout_seconds=config.proxy_health_check_timeout,
        health_check_url=config.proxy_health_check_url,
        unhealthy_threshold=config.proxy_unhealthy_threshold,
        recovery_interval_seconds=config.proxy_recovery_interval,
        selector_type=config.proxy_selector,
    )
    pool = ProxyPool(pool_config)
    for proxy in parse_proxy_list(config.proxy_list):
        pool.add_proxy(proxy)
    logger.info("代理池已初始化，共 %d 个代理", pool.proxy_count)
    return pool


def _build_retry_config(config: GatewayConfig) -> RetryConfig | None:
    """构建重试配置。"""
    if not config.retry_enabled:
        return None
    return RetryConfig(
        max_retries=config.retry_max_retries,
        initial_delay_ms=config.retry_initial_delay_ms,
        max_delay_ms=config.retry_max_delay_ms,
        multiplier=config.retry_multiplier,
    )


def _build_rate_limiter(
    config: GatewayConfig,
) -> MultiDimensionRateLimiter | None:
    """构建限流器。"""
    if not config.rate_limit_enabled:
        return None
    dimension_map = {
        "api_key": LimitDimension.API_KEY,
        "ip": LimitDimension.IP,
        "user": LimitDimension.USER,
        "global": LimitDimension.GLOBAL,
    }
    dimension = dimension_map.get(
        config.rate_limit_dimension.lower(), LimitDimension.API_KEY
    )
    rate_limit_configs = [
        RateLimitConfig(
            requests_per_second=config.rate_limit_rps,
            burst_size=config.rate_limit_burst,
            dimension=dimension,
        ),
        RateLimitConfig(
            requests_per_second=config.rate_limit_global_rps,
            burst_size=config.rate_limit_global_burst,
            dimension=LimitDimension.GLOBAL,
        ),
    ]
    limiter = MultiDimensionRateLimiter(rate_limit_configs)
    logger.info(
        "限流器已初始化: %s RPS=%.1f, 全局 RPS=%.1f",
        dimension.value,
        config.rate_limit_rps,
        config.rate_limit_global_rps,
    )
    return limiter


def _build_state() -> GatewayState:
    """构建网关运行时状态。"""
    config = GatewayConfig.from_env()
    registry: LoadedRegistry = load_registry(config.registry_path)
    tool_rate_limiters = _build_tool_rate_limiters(registry)
    scrape_guard = ScrapeGuard(
        allowed_domains=config.allowed_domains,
        denied_domains=config.denied_domains,
        domain_rps=config.domain_rps,
        domain_concurrency=config.domain_concurrency,
        cache_ttl_seconds=config.cache_ttl_seconds,
        robots_require_allow=config.robots_require_allow,
        tos_check_enabled=config.tos_check_enabled,
        tos_require_allow=config.tos_require_allow,
        tos_cache_ttl_seconds=config.tos_cache_ttl_seconds,
    )
    guard_store = ScrapeGuardStore(config.db_dsn) if config.guard_use_db else None
    minio_client = Minio(
        config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        secure=config.minio_secure,
    )
    proxy_pool = _build_proxy_pool(config)
    retry_config = _build_retry_config(config)
    rate_limiter = _build_rate_limiter(config)
    state = GatewayState(
        config=config,
        registry=registry,
        tool_rate_limiters=tool_rate_limiters,
        registry_reloader=None,
        scrape_guard=scrape_guard,
        guard_store=guard_store,
        minio_client=minio_client,
        proxy_pool=proxy_pool,
        retry_config=retry_config,
        rate_limiter=rate_limiter,
    )
    registry_reloader = RegistryReloader(
        registry=registry,
        on_reload=lambda reg: _update_tool_rate_limiters(state, reg),
    )
    state.registry_reloader = registry_reloader
    return state


def _get_domain_from_url(url: str) -> str | None:
    """从 URL 中提取域名。"""
    parsed = urlparse(url)
    return parsed.hostname


async def _request_with_retry(
    method: str,
    url: str,
    tool_name: str,
    state: GatewayState,
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
    files: Any | None = None,
    timeout_seconds: float | None = None,
) -> httpx.Response:
    """执行带代理和重试的 HTTP 请求。

    Args:
        method: HTTP 方法 (GET/POST)
        url: 请求 URL
        tool_name: 工具名称（用于日志）
        params: 查询参数
        json_data: JSON 请求体
        files: 文件上传
        timeout_seconds: 超时时间

    Returns:
        httpx.Response

    Raises:
        HTTPException: 请求失败
    """
    timeout = timeout_seconds or (state.config.timeout_ms / 1000.0)
    domain = _get_domain_from_url(url)
    current_proxy: ProxyConfig | None = None

    # 获取代理
    if state.proxy_pool is not None:
        current_proxy = state.proxy_pool.get_proxy(domain)
        if current_proxy is None:
            logger.debug("没有可用代理，使用直连")

    async def do_request() -> httpx.Response:
        proxy_url = current_proxy.to_url() if current_proxy else None
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=timeout,
            verify=state.config.mcp_tls_verify,
            trust_env=False,
        ) as client:
            if method == "GET":
                response = await client.get(url, params=params)
            elif method == "POST":
                response = await client.post(url, json=json_data, files=files)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")
            return response

    start_time = time.time()

    if state.retry_config is not None:
        # 使用重试机制
        result = await retry_async(
            func=do_request,
            config=state.retry_config,
            on_retry=lambda attempt: logger.debug(
                "重试 [%s]: 尝试 #%d, 错误: %s",
                tool_name,
                attempt.attempt_number,
                attempt.error_message,
            ),
        )
        latency_ms = (time.time() - start_time) * 1000

        if result.success and result.response is not None:
            if current_proxy and state.proxy_pool is not None:
                await state.proxy_pool.report_success(current_proxy, latency_ms)
            return result.response
        else:
            if current_proxy and state.proxy_pool is not None:
                await state.proxy_pool.report_failure(
                    current_proxy,
                    str(result.final_error) if result.final_error else "Unknown",
                )
            # 记录审计
            audit = create_audit_record(result, tool_name, url, method)
            logger.warning("请求失败 [%s]: %s", tool_name, audit)
            if result.final_error:
                raise HTTPException(
                    status_code=502, detail=str(result.final_error)
                ) from result.final_error
            if result.response:
                raise HTTPException(
                    status_code=result.response.status_code,
                    detail=result.response.text,
                )
            raise HTTPException(status_code=502, detail="请求失败")
    else:
        # 无重试，直接执行
        try:
            response = await do_request()
            latency_ms = (time.time() - start_time) * 1000
            if current_proxy and state.proxy_pool is not None:
                await state.proxy_pool.report_success(current_proxy, latency_ms)
            return response
        except httpx.RequestError as exc:
            if current_proxy and state.proxy_pool is not None:
                await state.proxy_pool.report_failure(current_proxy, str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc


app = FastAPI(title="baize-mcp-gateway", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    """启动时初始化。"""
    state = _ensure_state(app)

    # 启动代理池健康检查
    if state.proxy_pool is not None:
        await state.proxy_pool.start_health_check()
        logger.info("代理池健康检查已启动")

    # 启动配置文件监控
    if state.registry_reloader is not None:
        await state.registry_reloader.start_watch()

    if state.guard_store is None:
        return
    store = state.guard_store
    await store.connect()
    state.scrape_guard.attach_source(
        source=store.load_snapshot,
        refresh_seconds=state.config.guard_refresh_seconds,
    )

    async def _record_robots(
        tool_name: str,
        url: str,
        host: str,
        robots_url: str,
        allowed: bool,
        error_message: str | None,
        checked_at: datetime,
    ) -> None:
        await store.record_robots_check(
            tool_name=tool_name,
            url=url,
            host=host,
            robots_url=robots_url,
            allowed=allowed,
            error_message=error_message,
            checked_at=checked_at,
        )

    state.scrape_guard.attach_robots_audit(recorder=_record_robots)
    await state.scrape_guard.refresh_if_needed()


@app.on_event("shutdown")
async def shutdown() -> None:
    """关闭资源。"""
    state = _ensure_state(app)

    # 停止配置文件监控
    if state.registry_reloader is not None:
        await state.registry_reloader.stop_watch()

    # 停止代理池健康检查
    if state.proxy_pool is not None:
        await state.proxy_pool.stop_health_check()
        logger.info("代理池健康检查已停止")

    if state.guard_store is None:
        return
    await state.guard_store.close()


def _ensure_state(app: FastAPI) -> GatewayState:
    """确保网关状态已初始化。"""
    state = getattr(app.state, "gateway", None)
    if state is None:
        state = _build_state()
        app.state.gateway = state
    return state


def _get_state(request: Request) -> GatewayState:
    """从请求中获取运行时状态。"""
    return _ensure_state(request.app)


def _require_api_key(
    request: Request, authorization: str | None = Header(default=None)
) -> str:
    """校验 API Key 并返回 token。"""
    state = _get_state(request)
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少 Authorization")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization 格式错误")
    token = authorization.removeprefix("Bearer ").strip()
    if token != state.config.api_key:
        raise HTTPException(status_code=401, detail="API Key 无效")
    return token


def _get_client_ip(request: Request) -> str:
    """获取客户端 IP。"""
    # 优先从 X-Forwarded-For 头获取（代理场景）
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # 直接连接场景
    if request.client:
        return request.client.host
    return "unknown"


async def _check_rate_limit(
    request: Request,
    api_key: str,
    state: GatewayState,
) -> None:
    """检查请求是否被限流。"""
    if state.rate_limiter is None:
        return
    client_ip = _get_client_ip(request)
    result = await state.rate_limiter.check(api_key=api_key, ip=client_ip)
    if not result.allowed:
        headers = result.to_headers()
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后重试",
            headers=headers,
        )


async def _check_tool_rate_limit(
    tool_name: str,
    api_key: str,
    state: GatewayState,
) -> None:
    """检查工具级限流。"""
    limiter = state.tool_rate_limiters.get(tool_name)
    if limiter is None:
        return
    result = await limiter.check(api_key=api_key)
    if not result.allowed:
        headers = result.to_headers()
        raise HTTPException(
            status_code=429,
            detail=f"工具 {tool_name} 请求过于频繁，请稍后重试",
            headers=headers,
        )


def _check_tool_permission(
    tool: ToolConfig,
    user_roles: list[str] | None = None,
) -> None:
    """检查工具访问权限。

    Args:
        tool: 工具配置
        user_roles: 用户角色列表（暂未实现用户角色系统，预留接口）
    """
    if not tool.allowed_roles:
        # 没有配置角色限制，允许访问
        return
    if user_roles is None:
        user_roles = []
    # 检查是否有任意一个角色匹配
    if not any(role in tool.allowed_roles for role in user_roles):
        raise HTTPException(
            status_code=403,
            detail=f"无权访问此工具，需要角色: {', '.join(tool.allowed_roles)}",
        )


def _get_tool(tool_name: str, state: GatewayState) -> ToolConfig:
    """获取工具配置。"""

    tool = state.registry.tools.get(tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail="工具未注册")
    return tool


def _require_str(payload: dict[str, object], key: str) -> str:
    """读取必填字符串。"""

    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"缺少或非法参数: {key}")
    return value.strip()


def _require_int(payload: dict[str, object], key: str) -> int:
    """读取必填整数。"""

    value = payload.get(key)
    if not isinstance(value, int):
        raise HTTPException(status_code=400, detail=f"缺少或非法参数: {key}")
    if value <= 0:
        raise HTTPException(status_code=400, detail=f"参数 {key} 必须大于 0")
    return value


def _map_time_range(value: str) -> str | None:
    """映射时间范围。"""

    mapping = {
        "7d": "day",
        "30d": "month",
        "1y": "year",
        "all": None,
        "day": "day",
        "week": "week",
        "month": "month",
        "year": "year",
    }
    if value not in mapping:
        raise HTTPException(status_code=400, detail="time_range 不支持")
    return mapping[value]


def _normalize_source(result: dict[str, object]) -> str:
    """提取来源。"""

    engines = result.get("engines")
    if isinstance(engines, list) and engines:
        first = engines[0]
        if isinstance(first, str) and first:
            return first
    engine = result.get("engine")
    if isinstance(engine, str) and engine:
        return engine
    raise HTTPException(status_code=502, detail="上游缺少来源字段")


def _normalize_snippet(result: dict[str, object]) -> str:
    """提取摘要。"""

    content = result.get("content")
    if isinstance(content, str) and content:
        return content
    snippet = result.get("snippet")
    if isinstance(snippet, str) and snippet:
        return snippet
    raise HTTPException(status_code=502, detail="上游缺少摘要字段")


def _normalize_score(result: dict[str, object]) -> float:
    """提取评分。"""

    score = result.get("score")
    if isinstance(score, (int, float)):
        value = float(score)
        if value >= 0.0:
            return min(value, 1.0)
    raise HTTPException(status_code=502, detail="上游 score 不合法")


def _normalize_mime_type(raw: str) -> str:
    """规范化 MIME 类型。"""

    return raw.split(";", 1)[0].strip().lower()


def _ensure_mime_allowed(raw: str, state: GatewayState) -> str:
    """校验 MIME 类型白名单。"""

    normalized = _normalize_mime_type(raw)
    if (
        state.config.allowed_mime_types
        and normalized not in state.config.allowed_mime_types
    ):
        raise HTTPException(status_code=415, detail="mime_type 不在允许列表")
    return normalized


def _ensure_max_bytes(payload: bytes, *, label: str, state: GatewayState) -> None:
    """校验最大字节数。"""

    if len(payload) > state.config.max_content_bytes:
        raise HTTPException(status_code=413, detail=f"{label} 体积超限")


def _serialize_result(payload: dict[str, object] | None) -> str | None:
    """序列化结果用于审计。"""

    if payload is None:
        return None
    try:
        return json.dumps(payload, ensure_ascii=True)[:512]
    except TypeError:
        return str(payload)[:512]


async def _invoke_firecrawl(
    tool: ToolConfig, payload: dict[str, object], state: GatewayState
) -> dict[str, object]:
    """调用 Firecrawl 并输出 Artifact。"""

    url = _require_str(payload, "url")
    body: dict[str, Any] = {
        "url": url,
        "formats": ["markdown"],
        "waitFor": 3000,        # 等待页面 JavaScript 加载
        "timeout": 60000,       # 60秒超时
    }
    response = await _request_with_retry(
        method="POST",
        url=tool.url,
        tool_name="firecrawl",
        state=state,
        json_data=body,
        timeout_seconds=60.0,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    _ensure_max_bytes(response.content, label="response", state=state)
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="上游返回非 JSON") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="上游返回格式错误")
    success = data.get("success")
    if success is not True:
        raise HTTPException(status_code=502, detail="Firecrawl 返回失败")
    result = data.get("data")
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Firecrawl 返回缺少 data")
    markdown = result.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise HTTPException(status_code=502, detail="Firecrawl 返回缺少 markdown")
    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=502, detail="Firecrawl 返回缺少 metadata")
    markdown_bytes = markdown.encode("utf-8")
    _ensure_max_bytes(markdown_bytes, label="markdown", state=state)
    fetched_at = datetime.now(UTC)
    content_hash = sha256(markdown_bytes).hexdigest()
    storage_ref = _write_minio_text(markdown, content_hash, state)
    source_url = metadata.get("sourceURL")
    if not isinstance(source_url, str) or not source_url:
        source_url = url
    mime_type = metadata.get("contentType")
    if not isinstance(mime_type, str) or not mime_type:
        mime_type = "text/markdown"
    mime_type = _ensure_mime_allowed(mime_type, state)
    return {
        "artifact": {
            "artifact_uid": f"art_{content_hash}",
            "source_url": source_url,
            "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
            "content_sha256": f"sha256:{content_hash}",
            "mime_type": mime_type,
            "storage_ref": storage_ref,
        }
    }


def _write_minio_text(text: str, content_hash: str, state: GatewayState) -> str:
    """写入 Markdown 内容到 MinIO。"""

    object_name = f"firecrawl/{content_hash}.md"
    payload = text.encode("utf-8")
    state.minio_client.put_object(
        state.config.minio_bucket,
        object_name,
        data=io.BytesIO(payload),
        length=len(payload),
        content_type="text/markdown",
    )
    return object_name


def _coerce_query_params(
    payload: dict[str, object],
) -> dict[str, str | int | float | bool]:
    """校验并转换查询参数。"""

    params: dict[str, str | int | float | bool] = {}
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)):
            params[key] = value
            continue
        raise HTTPException(status_code=400, detail=f"参数 {key} 不能作为查询参数")
    return params


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[tuple[str, int, int]]:
    """按长度切分文本。"""

    if chunk_size <= 0:
        raise HTTPException(status_code=400, detail="chunk_size 必须大于 0")
    if overlap < 0 or overlap >= chunk_size:
        raise HTTPException(status_code=400, detail="chunk_overlap 不合法")
    chunks: list[tuple[str, int, int]] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunk_text = text[start:end]
        chunks.append((chunk_text, start, end))
        if end == length:
            break
        start = end - overlap
    return chunks


def _parse_archivebox_timestamp(raw: str) -> datetime:
    """解析 ArchiveBox 时间戳。

    支持两种格式:
    - v0.7.3+: Unix 时间戳 (如 "1769735924")
    - 旧版本: %Y%m%d%H%M%S 格式 (如 "20261130011844")
    """

    # 尝试 Unix 时间戳格式 (v0.7.3+)
    try:
        ts = int(raw)
        return datetime.fromtimestamp(ts, tz=UTC)
    except (ValueError, OSError):
        pass

    # 尝试旧格式 %Y%m%d%H%M%S
    try:
        return datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail=f"ArchiveBox 时间戳格式错误: {raw}"
        ) from exc


def _normalize_archivebox_payload(stdout: str) -> dict[str, object]:
    """解析 ArchiveBox 输出。

    v0.7.3 的输出格式为多行 pretty-printed JSON，需要提取完整 JSON 块。
    """

    payload: dict[str, object] | None = None

    # 方法 1: 尝试找到 JSON 数组/对象的起始位置并解析
    # ArchiveBox 输出可能包含 [i] 等信息行，JSON 以 [ 或 { 开头
    for start_char in ("[", "{"):
        idx = stdout.find(start_char)
        if idx >= 0:
            try:
                data = json.loads(stdout[idx:])
                if isinstance(data, list) and data:
                    first = data[0]
                    if isinstance(first, dict):
                        payload = first
                        break
                elif isinstance(data, dict):
                    payload = data
                    break
            except json.JSONDecodeError:
                continue

    # 方法 2: 回退到逐行解析（兼容单行 JSON 输出）
    if payload is None:
        lines = [line for line in stdout.splitlines() if line.strip()]
        for line in lines:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict):
                    payload = first
                    break
            if isinstance(data, dict):
                payload = data
                break

    if payload is None:
        raise HTTPException(status_code=502, detail="ArchiveBox 输出缺少 JSON")
    return payload


def _archivebox_field(payload: dict[str, object], *keys: str) -> str:
    """提取 ArchiveBox 字段。"""

    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HTTPException(status_code=502, detail="ArchiveBox 输出缺少必要字段")


async def _invoke_archivebox(
    tool: ToolConfig, payload: dict[str, object], state: GatewayState
) -> dict[str, object]:
    """调用 ArchiveBox 并输出 Artifact。"""

    url = _require_str(payload, "url")

    # Step 1: 添加 URL 到 ArchiveBox（不带 --json，v0.7.3 不支持）
    add_command = [
        "docker",
        "exec",
        "--user",
        state.config.archivebox_user,
        state.config.archivebox_container,
        "archivebox",
        "add",
        url,
    ]

    def _run_add() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            add_command,
            capture_output=True,
            text=True,
            check=False,
        )

    result = await asyncio.to_thread(_run_add)
    if result.returncode != 0:
        raise HTTPException(
            status_code=502, detail=result.stderr.strip() or "ArchiveBox add 执行失败"
        )

    # Step 2: 使用 list --json 获取归档结果
    list_command = [
        "docker",
        "exec",
        "--user",
        state.config.archivebox_user,
        state.config.archivebox_container,
        "archivebox",
        "list",
        "--json",
        "--filter-type=exact",
        url,
    ]

    def _run_list() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list_command,
            capture_output=True,
            text=True,
            check=False,
        )

    list_result = await asyncio.to_thread(_run_list)
    if list_result.returncode != 0:
        raise HTTPException(
            status_code=502, detail=list_result.stderr.strip() or "ArchiveBox list 执行失败"
        )

    data = _normalize_archivebox_payload(list_result.stdout)
    # v0.7.3 的 timestamp 格式为 "1769735924.527822"
    raw_timestamp = _archivebox_field(data, "timestamp")
    # 去掉小数点用于目录名
    timestamp = raw_timestamp.split(".")[0] if "." in raw_timestamp else raw_timestamp
    source_url = _archivebox_field(data, "url", "original_url")
    # v0.7.3 使用 hash 字段，不是 content_sha256
    content_hash = data.get("hash") or data.get("content_sha256") or f"sha256:{timestamp}"
    if not isinstance(content_hash, str):
        content_hash = f"sha256:{timestamp}"
    # v0.7.3 没有 mime_type，使用默认值
    mime_type = data.get("mime_type") or data.get("content_type") or "text/html"
    if not isinstance(mime_type, str):
        mime_type = "text/html"
    mime_type = _ensure_mime_allowed(mime_type, state)
    fetched_at = _parse_archivebox_timestamp(timestamp)
    storage_ref = f"http://{state.config.archivebox_host}:{state.config.archivebox_port}/archive/{raw_timestamp}/"

    return {
        "artifact": {
            "artifact_uid": f"art_{timestamp}",
            "source_url": source_url,
            "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
            "content_sha256": content_hash,
            "mime_type": mime_type,
            "storage_ref": storage_ref,
        }
    }


async def _read_minio_object(object_name: str, state: GatewayState) -> bytes:
    """从 MinIO 读取对象内容。"""

    def _read() -> bytes:
        response = state.minio_client.get_object(state.config.minio_bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await asyncio.to_thread(_read)


def _is_archivebox_directory_url(url: str) -> bool:
    """检测是否为 ArchiveBox 归档目录 URL。

    ArchiveBox 目录 URL 格式: http://host:port/archive/{timestamp}/
    """
    import re

    # 匹配 /archive/{timestamp}/ 格式
    return bool(re.search(r"/archive/\d+(\.\d+)?/?$", url))


async def _fetch_artifact_from_url(url: str, state: GatewayState) -> bytes:
    """从 HTTP URL 获取 artifact 内容（支持 ArchiveBox 等外部存储）。

    对于 ArchiveBox 归档目录 URL，自动获取实际内容文件（htmltotext.txt）
    而不是目录索引页面。
    """
    # 检测是否为 ArchiveBox 目录 URL
    if _is_archivebox_directory_url(url):
        # 确保 URL 以 / 结尾
        base_url = url.rstrip("/") + "/"

        # 优先尝试获取文本内容文件
        content_files = [
            "htmltotext.txt",  # 纯文本，最适合文档解析
            "readability/content.txt",  # Readability 提取的文本
            "mercury/content.txt",  # Mercury 提取的文本
        ]

        for content_file in content_files:
            content_url = base_url + content_file
            try:
                response = await _request_with_retry(
                    method="GET",
                    url=content_url,
                    tool_name="doc_parse",
                    state=state,
                    timeout_seconds=60.0,
                )
                if response.status_code == 200 and len(response.content) > 100:
                    logger.info(
                        "ArchiveBox: 从 %s 获取到内容 (%d bytes)",
                        content_file,
                        len(response.content),
                    )
                    return response.content
            except Exception as e:
                logger.debug("ArchiveBox: 尝试获取 %s 失败: %s", content_file, e)
                continue

        # 如果文本文件都获取失败，尝试获取 HTML 文件
        html_files = [
            "singlefile.html",  # SingleFile 保存的完整 HTML
            "output.html",  # ArchiveBox 输出的 HTML
        ]

        for html_file in html_files:
            html_url = base_url + html_file
            try:
                response = await _request_with_retry(
                    method="GET",
                    url=html_url,
                    tool_name="doc_parse",
                    state=state,
                    timeout_seconds=60.0,
                )
                if response.status_code == 200 and len(response.content) > 100:
                    logger.info(
                        "ArchiveBox: 从 %s 获取到内容 (%d bytes)",
                        html_file,
                        len(response.content),
                    )
                    return response.content
            except Exception as e:
                logger.debug("ArchiveBox: 尝试获取 %s 失败: %s", html_file, e)
                continue

        # 所有尝试都失败，抛出错误
        raise HTTPException(
            status_code=502,
            detail=f"ArchiveBox 归档内容获取失败，目录 URL: {url}",
        )

    # 非 ArchiveBox URL，直接获取
    response = await _request_with_retry(
        method="GET",
        url=url,
        tool_name="doc_parse",
        state=state,
        timeout_seconds=60.0,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"获取 artifact 失败: {response.status_code} {url}",
        )
    return response.content


async def _invoke_unstructured(
    tool: ToolConfig, payload: dict[str, object], state: GatewayState
) -> dict[str, object]:
    """调用 Unstructured 并输出 Chunk。"""

    artifact_uid = _require_str(payload, "artifact_uid")
    chunk_size = _require_int(payload, "chunk_size")
    chunk_overlap = _require_int(payload, "chunk_overlap")
    if state.guard_store is None:
        raise HTTPException(status_code=500, detail="未启用数据库读取")
    storage_ref, mime_type = await state.guard_store.get_artifact(artifact_uid)
    mime_type = _ensure_mime_allowed(mime_type, state)
    # 支持两种存储：HTTP URL（archive_url）和 MinIO 路径（web_crawl）
    if storage_ref.startswith("http://") or storage_ref.startswith("https://"):
        raw_bytes = await _fetch_artifact_from_url(storage_ref, state)
    else:
        raw_bytes = await _read_minio_object(storage_ref, state)
    _ensure_max_bytes(raw_bytes, label="artifact", state=state)

    files = {"files": (f"{artifact_uid}", raw_bytes, mime_type)}
    response = await _request_with_retry(
        method="POST",
        url=tool.url,
        tool_name="unstructured",
        state=state,
        files=files,
        timeout_seconds=60.0,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    _ensure_max_bytes(response.content, label="response", state=state)
    try:
        elements = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="上游返回非 JSON") from exc
    if not isinstance(elements, list):
        raise HTTPException(status_code=502, detail="上游解析结果格式错误")

    texts: list[str] = []
    for item in elements:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    if not texts:
        raise HTTPException(status_code=502, detail="解析结果为空")
    merged = "\n".join(texts)
    chunks = []
    for chunk_text, start, end in _chunk_text(merged, chunk_size, chunk_overlap):
        text_hash = sha256(chunk_text.encode("utf-8")).hexdigest()
        chunks.append(
            {
                "chunk_uid": f"chk_{sha256(f'{artifact_uid}:{start}:{end}'.encode()).hexdigest()}",
                "artifact_uid": artifact_uid,
                "anchor": {"type": "text_offset", "ref": f"{start}-{end}"},
                "text": chunk_text,
                "text_sha256": text_hash,
            }
        )
    return {"chunks": chunks}


async def _invoke_searxng(
    tool: ToolConfig, payload: dict[str, object], state: GatewayState
) -> dict[str, object]:
    """调用 SearxNG 并规范化输出。"""

    if tool.method != "GET":
        raise HTTPException(status_code=400, detail="SearxNG 仅支持 GET")
    query = _require_str(payload, "query")
    max_results = _require_int(payload, "max_results")
    if max_results > 50:
        raise HTTPException(status_code=400, detail="max_results 超过上限")
    language = _require_str(payload, "language")
    time_range = _require_str(payload, "time_range")
    mapped_range = _map_time_range(time_range)
    categories = payload.get("categories")
    if categories is not None and not isinstance(categories, str):
        raise HTTPException(status_code=400, detail="categories 必须为字符串")
    params: dict[str, str | int | float | bool] = {
        "q": query,
        "format": "json",
        "language": language,
        "pageno": 1,
    }
    if mapped_range is not None:
        params["time_range"] = mapped_range
    if isinstance(categories, str) and categories.strip():
        params["categories"] = categories.strip()

    response = await _request_with_retry(
        method="GET",
        url=tool.url,
        tool_name="searxng",
        state=state,
        params=params,
        timeout_seconds=state.config.timeout_ms / 1000.0,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    _ensure_max_bytes(response.content, label="response", state=state)
    try:
        resp_payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="上游返回非 JSON") from exc

    results = resp_payload.get("results")
    if not isinstance(results, list):
        raise HTTPException(status_code=502, detail="上游结果格式错误")
    normalized: list[dict[str, object]] = []
    for item in results[:max_results]:
        if not isinstance(item, dict):
            raise HTTPException(status_code=502, detail="上游结果格式错误")
        url = item.get("url")
        title = item.get("title")
        if not isinstance(url, str) or not url:
            raise HTTPException(status_code=502, detail="上游缺少 url")
        if not isinstance(title, str) or not title:
            raise HTTPException(status_code=502, detail="上游缺少 title")
        normalized.append(
            {
                "url": url,
                "title": title,
                "snippet": _normalize_snippet(item),
                "source": _normalize_source(item),
                "published_at": item.get("publishedDate") or item.get("published_at"),
                "score": _normalize_score(item),
            }
        )
    return {"results": normalized}


AdapterHandler = Callable[
    [ToolConfig, dict[str, object], GatewayState], Awaitable[dict[str, object]]
]

_ADAPTER_HANDLERS: dict[str, AdapterHandler] = {
    "searxng": _invoke_searxng,
    "unstructured": _invoke_unstructured,
    "archivebox": _invoke_archivebox,
    "firecrawl": _invoke_firecrawl,
}


def _requires_guard(tool: ToolConfig, tool_name: str) -> bool:
    """判断是否需要外联治理。"""
    return tool_name in {"web_crawl", "archive_url"} or tool.adapter == "firecrawl"


def _cache_and_return(
    *,
    state: GatewayState,
    tool_name: str,
    payload: dict[str, object],
    response: dict[str, object],
    target_url: str | None,
) -> dict[str, object]:
    """统一缓存写入并返回结果。"""
    state.scrape_guard.cache_set(
        tool_name=tool_name,
        payload=payload,
        response=response,
    )
    if target_url is not None:
        state.scrape_guard.cache_set_url(
            tool_name=tool_name, url=target_url, response=response
        )
    return response


async def _invoke_adapter(
    tool: ToolConfig, payload: dict[str, object], state: GatewayState
) -> dict[str, object]:
    """调用适配器。"""
    if tool.adapter is None:
        raise HTTPException(status_code=500, detail="适配器未配置")
    handler = _ADAPTER_HANDLERS.get(tool.adapter)
    if handler is None:
        raise HTTPException(status_code=400, detail="适配器类型不支持")
    return await handler(tool, payload, state)


def _parse_trace_headers(
    request: Request,
) -> tuple[str, str | None, str | None, str | None]:
    """解析追踪头。"""
    return parse_trace_context(
        request.headers.get("X-Trace-ID"),
        request.headers.get("X-Policy-Decision-ID"),
    )


async def _apply_scrape_guard(
    *,
    state: GatewayState,
    tool_name: str,
    tool: ToolConfig,
    payload: dict[str, object],
) -> tuple[str | None, asyncio.Semaphore | None, dict[str, object] | None]:
    """执行外联治理并检查 URL 缓存。"""
    if not _requires_guard(tool, tool_name):
        return None, None, None
    target_url = _require_str(payload, "url")
    try:
        semaphore = await state.scrape_guard.enforce(
            url=target_url,
            tool_name=tool_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    cached = state.scrape_guard.cache_get_url(tool_name=tool_name, url=target_url)
    return target_url, semaphore, cached


async def _record_tool_trace(
    *,
    state: GatewayState,
    trace_id: str,
    tool_name: str,
    started_at: datetime,
    duration_ms: int,
    error: Exception | None,
    result_ref: str | None,
    caller_trace_id: str | None,
    caller_policy_decision_id: str | None,
) -> None:
    """记录工具调用审计。"""
    if state.guard_store is None:
        return
    error_type = type(error).__name__ if error is not None else None
    error_message = str(error) if error is not None else None
    await state.guard_store.record_tool_trace(
        trace_id=trace_id,
        tool_name=tool_name,
        started_at=started_at,
        duration_ms=duration_ms,
        success=error is None,
        error_type=error_type,
        error_message=error_message,
        result_ref=result_ref,
        policy_decision_id=caller_policy_decision_id,
        caller_trace_id=caller_trace_id,
        caller_policy_decision_id=caller_policy_decision_id,
    )


@app.get("/health")
def health() -> dict[str, str]:
    """健康检查。"""

    return {"status": "ok"}


@app.get("/proxy/stats")
def proxy_stats(request: Request) -> dict[str, object]:
    """获取代理池统计信息。"""

    state = _get_state(request)
    if state.proxy_pool is None:
        return {"enabled": False, "message": "代理池未启用"}
    stats = state.proxy_pool.get_statistics()
    stats["enabled"] = True
    return stats


@app.get("/rate-limit/stats")
def rate_limit_stats(request: Request) -> dict[str, object]:
    """获取限流统计信息。"""
    state = _get_state(request)
    if state.rate_limiter is None:
        return {"enabled": False, "message": "限流未启用"}
    stats = state.rate_limiter.get_stats()
    stats["enabled"] = True
    return stats


@app.get("/admin/registry/stats")
def registry_stats(
    request: Request,
    _: str = Depends(_require_api_key),
) -> dict[str, object]:
    """获取注册表统计信息。"""
    state = _get_state(request)
    if state.registry_reloader is None:
        return {"watching": False, "message": "注册表监控未初始化"}
    return state.registry_reloader.get_stats()


@app.get("/admin/scrape-guard/stats")
def scrape_guard_stats(
    request: Request,
    _: str = Depends(_require_api_key),
) -> dict[str, object]:
    """获取 Scrape Guard 缓存统计信息。"""
    state = _get_state(request)
    return state.scrape_guard.get_cache_stats()


@app.get("/admin/audit/tools/{trace_id}")
async def get_audit_tool_trace(
    trace_id: str, request: Request, _: str = Depends(_require_api_key)
) -> dict[str, object]:
    """获取单个工具调用审计记录。"""

    state = _get_state(request)
    if state.guard_store is None:
        raise HTTPException(status_code=500, detail="未启用数据库读取")
    record = await state.guard_store.get_tool_trace(trace_id)
    if record is None:
        raise HTTPException(status_code=404, detail="工具调用记录不存在")
    return record


@app.get("/admin/audit/decisions/{decision_id}")
async def get_audit_by_decision(
    decision_id: str, request: Request, _: str = Depends(_require_api_key)
) -> dict[str, object]:
    """按策略决策 ID 查询审计记录。"""

    state = _get_state(request)
    if state.guard_store is None:
        raise HTTPException(status_code=500, detail="未启用数据库读取")
    records = await state.guard_store.query_tool_traces_by_decision(decision_id)
    return {"decision_id": decision_id, "tool_traces": records}


@app.post("/admin/scrape-guard/clear-tos-cache")
def clear_tos_cache(
    request: Request,
    host: str | None = None,
    _: str = Depends(_require_api_key),
) -> dict[str, object]:
    """清理 ToS 缓存。

    Args:
        host: 指定域名，None 表示清理所有

    需要 API Key 认证。
    """
    state = _get_state(request)
    count = state.scrape_guard.clear_tos_cache(host)
    return {
        "success": True,
        "cleared_count": count,
        "host": host,
    }


@app.post("/admin/registry/reload")
def admin_reload(
    request: Request,
    _: str = Depends(_require_api_key),
) -> dict[str, object]:
    """手动重载工具注册表。

    需要 API Key 认证。
    """
    try:
        state = _get_state(request)
        if state.registry_reloader is None:
            raise HTTPException(status_code=500, detail="注册表监控未初始化")
        new_registry = state.registry_reloader.reload()
        return {
            "success": True,
            "message": "注册表已重载",
            "tool_count": len(new_registry.tools),
            "tools": list(new_registry.tools.keys()),
        }
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/tools/{tool_name}/invoke")
async def invoke_tool(
    tool_name: str,
    payload: dict[str, object],
    request: Request,
    api_key: str = Depends(_require_api_key),
) -> dict[str, object]:
    """调用工具。"""
    state = _get_state(request)
    # API 级限流检查
    await _check_rate_limit(request, api_key, state)

    (
        trace_id,
        caller_trace_id,
        caller_policy_decision_id,
        invalid_trace_id,
    ) = _parse_trace_headers(request)
    if invalid_trace_id:
        logger.warning("收到非法 trace_id，已忽略: %s", invalid_trace_id)
    started_at = datetime.now(UTC)
    start_ts = time.time()
    response_payload: dict[str, object] | None = None
    error: Exception | None = None
    semaphore: asyncio.Semaphore | None = None
    target_url: str | None = None

    try:
        tool = _get_tool(tool_name, state)

        # 工具级权限检查
        _check_tool_permission(tool)

        # 工具级限流检查
        await _check_tool_rate_limit(tool_name, api_key, state)

        await state.scrape_guard.refresh_if_needed()
        cached = state.scrape_guard.cache_get(tool_name=tool_name, payload=payload)
        if cached is not None:
            response_payload = cached
            return cached

        (
            target_url,
            semaphore,
            url_cached,
        ) = await _apply_scrape_guard(
            state=state,
            tool_name=tool_name,
            tool=tool,
            payload=payload,
        )
        if url_cached is not None:
            response_payload = url_cached
            return url_cached

        if tool.adapter is not None:
            adapter_payload = await _invoke_adapter(tool, payload, state)
            response_payload = _cache_and_return(
                state=state,
                tool_name=tool_name,
                payload=payload,
                response=adapter_payload,
                target_url=target_url,
            )
            return response_payload

        # 使用工具级超时配置
        timeout = tool.get_timeout_seconds(state.config.timeout_ms)
        if tool.method == "GET":
            response = await _request_with_retry(
                method="GET",
                url=tool.url,
                tool_name=tool_name,
                state=state,
                params=_coerce_query_params(payload),
                timeout_seconds=timeout,
            )
        else:
            response = await _request_with_retry(
                method="POST",
                url=tool.url,
                tool_name=tool_name,
                state=state,
                json_data=dict(payload),  # 转换为 dict[str, Any]
                timeout_seconds=timeout,
            )

        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        _ensure_max_bytes(response.content, label="response", state=state)
        try:
            raw_payload = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="上游返回非 JSON") from exc
        if not isinstance(raw_payload, dict):
            raise HTTPException(status_code=502, detail="上游返回格式错误")
        response_payload = raw_payload
        return _cache_and_return(
            state=state,
            tool_name=tool_name,
            payload=payload,
            response=response_payload,
            target_url=target_url,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        error = exc
        raise
    finally:
        if semaphore is not None:
            semaphore.release()
        duration_ms = int((time.time() - start_ts) * 1000)
        result_ref = _serialize_result(response_payload)
        try:
            await _record_tool_trace(
                state=state,
                trace_id=trace_id,
                tool_name=tool_name,
                started_at=started_at,
                duration_ms=duration_ms,
                error=error,
                result_ref=result_ref,
                caller_trace_id=caller_trace_id,
                caller_policy_decision_id=caller_policy_decision_id,
            )
        except Exception as audit_exc:  # pylint: disable=broad-exception-caught
            if error is not None:
                raise RuntimeError(
                    f"工具调用失败: {error}; 审计写入失败: {audit_exc}"
                ) from audit_exc
            raise
