"""配置加载。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# 自动加载 .env 文件
try:
    from dotenv import load_dotenv

    _ENV_CANDIDATES = [
        Path.cwd() / ".env",
        Path(__file__).parent.parent.parent.parent / ".env",
    ]
    for _env_path in _ENV_CANDIDATES:
        if _env_path.exists():
            load_dotenv(_env_path)
            break
except ImportError:
    pass  # python-dotenv 未安装时跳过


@dataclass(frozen=True)
class GatewayConfig:
    """网关配置。"""

    env: str
    api_key: str
    registry_path: Path
    timeout_ms: int
    host: str
    port: int
    allowed_domains: tuple[str, ...]
    denied_domains: tuple[str, ...]
    domain_rps: float
    domain_concurrency: int
    cache_ttl_seconds: int
    robots_require_allow: bool
    # ToS 检查配置
    tos_check_enabled: bool
    tos_require_allow: bool
    tos_cache_ttl_seconds: int
    db_dsn: str
    guard_refresh_seconds: int
    guard_use_db: bool
    max_content_bytes: int
    allowed_mime_types: tuple[str, ...]
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool
    minio_bucket: str
    archivebox_host: str
    archivebox_port: int
    archivebox_container: str
    archivebox_user: str
    # 代理池配置
    proxy_enabled: bool
    proxy_list: str
    proxy_health_check_interval: int
    proxy_health_check_timeout: int
    proxy_health_check_url: str
    proxy_unhealthy_threshold: int
    proxy_recovery_interval: int
    proxy_selector: str
    # 重试配置
    retry_enabled: bool
    retry_max_retries: int
    retry_initial_delay_ms: int
    retry_max_delay_ms: int
    retry_multiplier: float
    # TLS 配置
    mcp_tls_verify: bool
    # API 限流配置
    rate_limit_enabled: bool
    rate_limit_rps: float
    rate_limit_burst: int
    rate_limit_dimension: str
    rate_limit_global_rps: float
    rate_limit_global_burst: int

    @staticmethod
    def from_env() -> GatewayConfig:
        """从环境变量加载配置。"""

        env = os.getenv("MCP_GATEWAY_ENV", "dev")
        api_key = _require_env("MCP_API_KEY")
        registry_path = Path(_require_env("MCP_TOOL_REGISTRY_PATH")).expanduser()
        if not registry_path.exists():
            raise ValueError(f"工具注册表不存在: {registry_path}")
        timeout_ms = _require_int("MCP_REQUEST_TIMEOUT_MS")
        host = _require_env("MCP_HOST")
        port = _require_int("MCP_PORT")
        allowed_domains = _split_list(os.getenv("MCP_ALLOWED_DOMAINS", ""))
        denied_domains = _split_list(os.getenv("MCP_DENIED_DOMAINS", ""))
        domain_rps = _require_float("MCP_DOMAIN_RPS", default=2.0)
        domain_concurrency = _require_int("MCP_DOMAIN_CONCURRENCY", default=2)
        cache_ttl_seconds = _require_int("MCP_CACHE_TTL_SECONDS", default=300)
        robots_require_allow = _require_bool("MCP_ROBOTS_REQUIRE_ALLOW", default=True)
        # ToS 检查配置
        tos_check_enabled = _require_bool("MCP_TOS_CHECK_ENABLED", default=True)
        tos_require_allow = _require_bool("MCP_TOS_REQUIRE_ALLOW", default=False)
        tos_cache_ttl_seconds = _require_int("MCP_TOS_CACHE_TTL_SECONDS", default=86400)
        guard_use_db = _require_bool("MCP_GUARD_USE_DB", default=True)
        guard_refresh_seconds = _require_int("MCP_GUARD_REFRESH_SECONDS", default=60)
        db_dsn = _require_env("MCP_DB_DSN") if guard_use_db else ""
        max_content_bytes = _require_int("MCP_MAX_CONTENT_BYTES", default=5_000_000)
        allowed_mime_types = _split_list(
            os.getenv(
                "MCP_ALLOWED_MIME_TYPES",
                "text/html,text/plain,text/markdown,application/pdf,application/xhtml+xml",
            )
        )
        minio_endpoint = _require_env("MINIO_ENDPOINT")
        minio_access_key = _require_env("MINIO_ACCESS_KEY")
        minio_secret_key = _require_env("MINIO_SECRET_KEY")
        minio_secure = _require_bool("MINIO_SECURE", default=False)
        minio_bucket = _require_env("MINIO_BUCKET")
        archivebox_host = _require_env("ARCHIVEBOX_HOST")
        archivebox_port = _require_int("ARCHIVEBOX_PORT", default=8602)
        archivebox_container = _require_env("ARCHIVEBOX_CONTAINER")
        archivebox_user = _require_env("ARCHIVEBOX_USER")
        # 代理池配置
        proxy_enabled = _require_bool("MCP_PROXY_ENABLED", default=False)
        proxy_list = os.getenv("MCP_PROXY_LIST", "")
        proxy_health_check_interval = _require_int(
            "MCP_PROXY_HEALTH_CHECK_INTERVAL", default=60
        )
        proxy_health_check_timeout = _require_int(
            "MCP_PROXY_HEALTH_CHECK_TIMEOUT", default=10
        )
        proxy_health_check_url = os.getenv(
            "MCP_PROXY_HEALTH_CHECK_URL", "https://www.google.com"
        )
        proxy_unhealthy_threshold = _require_int(
            "MCP_PROXY_UNHEALTHY_THRESHOLD", default=3
        )
        proxy_recovery_interval = _require_int(
            "MCP_PROXY_RECOVERY_INTERVAL", default=300
        )
        proxy_selector = os.getenv("MCP_PROXY_SELECTOR", "round_robin")
        # 重试配置
        retry_enabled = _require_bool("MCP_RETRY_ENABLED", default=True)
        retry_max_retries = _require_int("MCP_RETRY_MAX_RETRIES", default=3)
        retry_initial_delay_ms = _require_int(
            "MCP_RETRY_INITIAL_DELAY_MS", default=1000
        )
        retry_max_delay_ms = _require_int("MCP_RETRY_MAX_DELAY_MS", default=30000)
        retry_multiplier = _require_float("MCP_RETRY_MULTIPLIER", default=2.0)
        # TLS 配置
        mcp_tls_verify = _require_bool("MCP_TLS_VERIFY", default=True)
        # API 限流配置
        rate_limit_enabled = _require_bool("MCP_RATE_LIMIT_ENABLED", default=True)
        rate_limit_rps = _require_float("MCP_RATE_LIMIT_RPS", default=10.0)
        rate_limit_burst = _require_int("MCP_RATE_LIMIT_BURST", default=20)
        rate_limit_dimension = os.getenv("MCP_RATE_LIMIT_DIMENSION", "api_key")
        rate_limit_global_rps = _require_float(
            "MCP_RATE_LIMIT_GLOBAL_RPS", default=100.0
        )
        rate_limit_global_burst = _require_int(
            "MCP_RATE_LIMIT_GLOBAL_BURST", default=200
        )
        return GatewayConfig(
            env=env,
            api_key=api_key,
            registry_path=registry_path,
            timeout_ms=timeout_ms,
            host=host,
            port=port,
            allowed_domains=allowed_domains,
            denied_domains=denied_domains,
            domain_rps=domain_rps,
            domain_concurrency=domain_concurrency,
            cache_ttl_seconds=cache_ttl_seconds,
            robots_require_allow=robots_require_allow,
            tos_check_enabled=tos_check_enabled,
            tos_require_allow=tos_require_allow,
            tos_cache_ttl_seconds=tos_cache_ttl_seconds,
            db_dsn=db_dsn,
            guard_refresh_seconds=guard_refresh_seconds,
            guard_use_db=guard_use_db,
            max_content_bytes=max_content_bytes,
            allowed_mime_types=allowed_mime_types,
            minio_endpoint=minio_endpoint,
            minio_access_key=minio_access_key,
            minio_secret_key=minio_secret_key,
            minio_secure=minio_secure,
            minio_bucket=minio_bucket,
            archivebox_host=archivebox_host,
            archivebox_port=archivebox_port,
            archivebox_container=archivebox_container,
            archivebox_user=archivebox_user,
            proxy_enabled=proxy_enabled,
            proxy_list=proxy_list,
            proxy_health_check_interval=proxy_health_check_interval,
            proxy_health_check_timeout=proxy_health_check_timeout,
            proxy_health_check_url=proxy_health_check_url,
            proxy_unhealthy_threshold=proxy_unhealthy_threshold,
            proxy_recovery_interval=proxy_recovery_interval,
            proxy_selector=proxy_selector,
            retry_enabled=retry_enabled,
            retry_max_retries=retry_max_retries,
            retry_initial_delay_ms=retry_initial_delay_ms,
            retry_max_delay_ms=retry_max_delay_ms,
            retry_multiplier=retry_multiplier,
            mcp_tls_verify=mcp_tls_verify,
            rate_limit_enabled=rate_limit_enabled,
            rate_limit_rps=rate_limit_rps,
            rate_limit_burst=rate_limit_burst,
            rate_limit_dimension=rate_limit_dimension,
            rate_limit_global_rps=rate_limit_global_rps,
            rate_limit_global_burst=rate_limit_global_burst,
        )


def _require_env(name: str) -> str:
    """读取必填环境变量。"""

    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"缺少必填环境变量: {name}")
    return value.strip()


def _require_int(name: str, *, default: int | None = None) -> int:
    """读取必填整数环境变量。"""

    raw = os.getenv(name)
    if raw is None or not raw.strip():
        if default is None:
            raise ValueError(f"缺少必填环境变量: {name}")
        return default
    raw = raw.strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须为整数") from exc
    if value <= 0:
        raise ValueError(f"环境变量 {name} 必须大于 0")
    return value


def _require_float(name: str, *, default: float | None = None) -> float:
    """读取必填浮点环境变量。"""

    raw = os.getenv(name)
    if raw is None or not raw.strip():
        if default is None:
            raise ValueError(f"缺少必填环境变量: {name}")
        return default
    raw = raw.strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须为数字") from exc
    if value <= 0:
        raise ValueError(f"环境变量 {name} 必须大于 0")
    return value


def _require_bool(name: str, *, default: bool | None = None) -> bool:
    """读取必填布尔环境变量。"""

    raw = os.getenv(name)
    if raw is None or not raw.strip():
        if default is None:
            raise ValueError(f"缺少必填环境变量: {name}")
        return default
    value = raw.strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    raise ValueError(f"环境变量 {name} 必须是 true/false")


def _split_list(value: str) -> tuple[str, ...]:
    """解析逗号分隔列表。"""

    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    return tuple(items)
