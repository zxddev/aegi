"""配置加载。

支持延迟加载 .env 文件，避免模块导入时的副作用。
可通过 BAIZE_CORE_SKIP_DOTENV=true 跳过 .env 加载（用于测试环境）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from baize_core.schemas.policy import RiskLevel

# .env 文件候选路径
# 优先级：当前目录 > baize-core 目录 > 项目根目录
_env_candidates = [
    Path.cwd() / ".env",
    Path(__file__).parent.parent.parent.parent / ".env",  # baize-core/.env
    Path(__file__).parent.parent.parent.parent.parent / ".env",  # 项目根/.env
]

# 延迟加载标记
_ENV_LOADED = False


def _load_env_if_needed() -> None:
    """延迟加载 .env 文件。

    - 仅在首次调用 get_settings() 时加载
    - 可通过 BAIZE_CORE_SKIP_DOTENV=true 跳过加载（测试环境）
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    # 检查是否跳过 .env 加载（测试环境）
    if os.getenv("BAIZE_CORE_SKIP_DOTENV", "").lower() in {"true", "1", "yes"}:
        _ENV_LOADED = True
        return

    # 按优先级加载 .env 文件
    for env_file in _env_candidates:
        if env_file.exists():
            load_dotenv(env_file)
            break

    _ENV_LOADED = True


def _split_list(value: str) -> tuple[str, ...]:
    """解析逗号分隔列表。"""

    items = [item.strip() for item in value.split(",") if item.strip()]
    return tuple(items)


def _read_int(name: str, *, default: int) -> int:
    """读取可选整数环境变量。"""

    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须为整数") from exc
    if value <= 0:
        raise ValueError(f"环境变量 {name} 必须大于 0")
    return value


def _read_bool(name: str, *, default: bool) -> bool:
    """读取可选布尔环境变量。"""

    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    raise ValueError(f"环境变量 {name} 必须是 true/false")


def _parse_risk_level(value: str) -> RiskLevel:
    """解析风险等级字符串。"""

    normalized = value.strip().lower()
    if normalized == "low":
        return RiskLevel.LOW
    if normalized == "medium":
        return RiskLevel.MEDIUM
    if normalized == "high":
        return RiskLevel.HIGH
    raise ValueError(f"风险等级不支持: {value}")


def _parse_risk_levels(value: str) -> tuple[RiskLevel, ...]:
    """解析风险等级列表。"""

    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        return tuple()
    return tuple(_parse_risk_level(item) for item in items)


def _parse_tool_risk_levels(value: str) -> dict[str, RiskLevel]:
    """解析工具风险等级映射。"""

    mapping: dict[str, RiskLevel] = {}
    items = [item.strip() for item in value.split(",") if item.strip()]
    for item in items:
        if ":" not in item:
            raise ValueError(f"工具风险等级格式错误: {item}")
        tool_name, risk = item.split(":", 1)
        tool_name = tool_name.strip()
        if not tool_name:
            raise ValueError("工具名称不能为空")
        mapping[tool_name] = _parse_risk_level(risk)
    return mapping


def _require_env(name: str) -> str:
    """读取必填环境变量。"""

    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"缺少必填环境变量: {name}")
    return value.strip()


def _require_bool(name: str) -> bool:
    """读取必填布尔环境变量。"""

    value = _require_env(name).lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    raise ValueError(f"环境变量 {name} 必须是 true/false")


@dataclass(frozen=True)
class PolicyConfig:
    """策略引擎配置。"""

    allowed_models: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    default_allow: bool
    enforced_timeout_ms: int
    enforced_max_pages: int
    enforced_max_iterations: int
    enforced_min_sources: int
    enforced_max_concurrency: int
    require_archive_first: bool
    require_citations: bool
    hitl_risk_levels: tuple[RiskLevel, ...]
    tool_risk_levels: dict[str, RiskLevel]

    @classmethod
    def from_env(cls) -> PolicyConfig:
        """从环境变量加载策略配置。"""
        return cls(
            allowed_models=_split_list(os.getenv("BAIZE_CORE_ALLOWED_MODELS", "")),
            allowed_tools=_split_list(os.getenv("BAIZE_CORE_ALLOWED_TOOLS", "")),
            default_allow=(
                os.getenv("BAIZE_CORE_POLICY_DEFAULT_ALLOW", "false").lower() == "true"
            ),
            enforced_timeout_ms=_read_int("BAIZE_CORE_TOOL_TIMEOUT_MS", default=30000),
            enforced_max_pages=_read_int("BAIZE_CORE_TOOL_MAX_PAGES", default=20),
            enforced_max_iterations=_read_int("BAIZE_CORE_MAX_ITERATIONS", default=3),
            enforced_min_sources=_read_int("BAIZE_CORE_MIN_SOURCES", default=3),
            enforced_max_concurrency=_read_int("BAIZE_CORE_MAX_CONCURRENCY", default=5),
            require_archive_first=_read_bool(
                "BAIZE_CORE_REQUIRE_ARCHIVE_FIRST", default=True
            ),
            require_citations=_read_bool("BAIZE_CORE_REQUIRE_CITATIONS", default=True),
            hitl_risk_levels=_parse_risk_levels(
                os.getenv("BAIZE_CORE_HITL_RISK_LEVELS", "high")
            ),
            tool_risk_levels=_parse_tool_risk_levels(
                os.getenv(
                    "BAIZE_CORE_TOOL_RISK_LEVELS",
                    "web_crawl:high,archive_url:high",
                )
            ),
        )


@dataclass(frozen=True)
class AuditConfig:
    """审计配置。"""

    log_path: str

    @classmethod
    def from_env(cls) -> AuditConfig:
        """从环境变量加载审计配置。"""
        return cls(
            log_path=os.getenv("BAIZE_CORE_AUDIT_LOG", "output/baize_core_audit.jsonl")
        )


@dataclass(frozen=True)
class DatabaseConfig:
    """数据库配置。"""

    dsn: str

    @classmethod
    def from_env(cls) -> DatabaseConfig:
        """从环境变量加载数据库配置。"""
        return cls(dsn=_require_env("POSTGRES_DSN"))


@dataclass(frozen=True)
class MinioConfig:
    """MinIO 配置。"""

    endpoint: str
    access_key: str
    secret_key: str
    secure: bool
    bucket: str

    @classmethod
    def from_env(cls) -> MinioConfig:
        """从环境变量加载 MinIO 配置。"""
        return cls(
            endpoint=_require_env("MINIO_ENDPOINT"),
            access_key=_require_env("MINIO_ACCESS_KEY"),
            secret_key=_require_env("MINIO_SECRET_KEY"),
            secure=_require_bool("MINIO_SECURE"),
            bucket=_require_env("MINIO_BUCKET"),
        )


@dataclass(frozen=True)
class McpConfig:
    """MCP Gateway 配置。"""

    base_url: str
    api_key: str
    tls_verify: bool

    @classmethod
    def from_env(cls) -> McpConfig:
        """从环境变量加载 MCP 配置。"""
        return cls(
            base_url=_require_env("MCP_BASE_URL"),
            api_key=_require_env("MCP_API_KEY"),
            tls_verify=_require_bool("MCP_TLS_VERIFY"),
        )


@dataclass(frozen=True)
class Neo4jConfig:
    """Neo4j 配置。"""

    uri: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> Neo4jConfig:
        """从环境变量加载 Neo4j 配置。"""
        return cls(
            uri=_require_env("NEO4J_URI"),
            user=_require_env("NEO4J_USER"),
            password=_require_env("NEO4J_PASSWORD"),
        )


@dataclass(frozen=True)
class QdrantConfig:
    """Qdrant 配置。"""

    url: str
    grpc_url: str
    api_key: str

    @classmethod
    def from_env(cls) -> QdrantConfig:
        """从环境变量加载 Qdrant 配置。"""
        return cls(
            url=_require_env("QDRANT_URL"),
            grpc_url=_require_env("QDRANT_GRPC_URL"),
            api_key=os.getenv("QDRANT_API_KEY", ""),
        )


@dataclass(frozen=True)
class LlmConfig:
    """模型配置。"""

    provider: str
    model: str
    openai_api_key: str
    openai_api_base: str

    @classmethod
    def from_env(cls) -> LlmConfig:
        """从环境变量加载 LLM 配置。"""
        return cls(
            provider=_require_env("DEFAULT_LLM_PROVIDER"),
            model=_require_env("DEFAULT_MODEL"),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_api_base=os.getenv("OPENAI_API_BASE", "").strip(),
        )


@dataclass(frozen=True)
class OpenSearchConfig:
    """OpenSearch 配置。"""

    host: str
    port: int
    use_ssl: bool
    verify_certs: bool
    http_auth_user: str
    http_auth_password: str
    chunk_index: str
    audit_index: str

    @classmethod
    def from_env(cls) -> OpenSearchConfig:
        """从环境变量加载 OpenSearch 配置。"""
        return cls(
            host=os.getenv("OPENSEARCH_HOST", "localhost"),
            port=_read_int("OPENSEARCH_PORT", default=9200),
            use_ssl=_read_bool("OPENSEARCH_USE_SSL", default=False),
            verify_certs=_read_bool("OPENSEARCH_VERIFY_CERTS", default=True),
            http_auth_user=os.getenv("OPENSEARCH_USER", "admin"),
            http_auth_password=os.getenv("OPENSEARCH_PASSWORD", "admin"),
            chunk_index=os.getenv("OPENSEARCH_CHUNK_INDEX", "chunks"),
            audit_index=os.getenv("OPENSEARCH_AUDIT_INDEX", "audit_events"),
        )


@dataclass(frozen=True)
class StormConfig:
    """STORM 编排配置。"""

    skip_review_validation: bool  # 跳过 review 严格校验

    @classmethod
    def from_env(cls) -> StormConfig:
        """从环境变量加载 STORM 配置。"""
        return cls(
            skip_review_validation=_read_bool(
                "BAIZE_SKIP_REVIEW_VALIDATION", default=False
            ),
        )


@dataclass(frozen=True)
class AppConfig:
    """应用配置。"""

    env: str
    policy: PolicyConfig
    audit: AuditConfig
    llm: LlmConfig
    database: DatabaseConfig
    minio: MinioConfig
    mcp: McpConfig
    neo4j: Neo4jConfig
    qdrant: QdrantConfig
    opensearch: OpenSearchConfig
    storm: StormConfig

    @property
    def database_url(self) -> str:
        return self.database.dsn

    @property
    def minio_endpoint(self) -> str:
        return self.minio.endpoint

    @property
    def minio_access_key(self) -> str:
        return self.minio.access_key

    @property
    def minio_secret_key(self) -> str:
        return self.minio.secret_key

    @property
    def minio_secure(self) -> bool:
        return self.minio.secure

    @property
    def minio_bucket(self) -> str:
        return self.minio.bucket

    @property
    def neo4j_uri(self) -> str:
        return self.neo4j.uri

    @property
    def neo4j_user(self) -> str:
        return self.neo4j.user

    @property
    def neo4j_password(self) -> str:
        return self.neo4j.password

    @property
    def qdrant_url(self) -> str:
        return self.qdrant.url

    @property
    def qdrant_grpc_url(self) -> str:
        return self.qdrant.grpc_url

    @property
    def qdrant_api_key(self) -> str:
        return self.qdrant.api_key

    @classmethod
    def from_env(cls) -> AppConfig:
        """从环境变量加载配置。

        每个子配置自己负责加载，职责单一。
        """
        _load_env_if_needed()  # 确保 .env 已加载
        return cls(
            env=os.getenv("BAIZE_CORE_ENV", "dev"),
            policy=PolicyConfig.from_env(),
            audit=AuditConfig.from_env(),
            llm=LlmConfig.from_env(),
            database=DatabaseConfig.from_env(),
            minio=MinioConfig.from_env(),
            mcp=McpConfig.from_env(),
            neo4j=Neo4jConfig.from_env(),
            qdrant=QdrantConfig.from_env(),
            opensearch=OpenSearchConfig.from_env(),
            storm=StormConfig.from_env(),
        )


_SETTINGS: AppConfig | None = None


def get_settings() -> AppConfig:
    """获取配置（带缓存）。

    首次调用时会延迟加载 .env 文件，然后从环境变量构建配置。
    可通过 BAIZE_CORE_SKIP_DOTENV=true 跳过 .env 加载（测试环境）。
    """
    global _SETTINGS
    if _SETTINGS is None:
        _load_env_if_needed()  # 延迟加载 .env
        _SETTINGS = AppConfig.from_env()
    return _SETTINGS


def reset_settings() -> None:
    """重置配置缓存（仅用于测试）。

    调用此函数后，下次 get_settings() 会重新加载配置。
    """
    global _SETTINGS, _ENV_LOADED
    _SETTINGS = None
    _ENV_LOADED = False
