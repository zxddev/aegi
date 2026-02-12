# Author: msq
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AEGI_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    postgres_dsn_async: str = "postgresql+asyncpg://aegi:aegi@localhost:8710/aegi"
    postgres_dsn_sync: str = "postgresql+psycopg://aegi:aegi@localhost:8710/aegi"
    mcp_gateway_base_url: str = "http://localhost:8704"

    # LLM Proxy (AntiHub Plugin API, OpenAI兼容)
    litellm_base_url: str = "http://localhost:8045"
    litellm_api_key: str = "sk-aegi-dev"
    litellm_default_model: str = "claude-sonnet-4-20250514"
    litellm_fast_model: str = "claude-sonnet-4-20250514"
    litellm_embedding_model: str = "embedding"
    litellm_extra_headers: str = ""  # JSON dict, e.g. '{"X-Account-Type":"kiro"}'

    # 本地 embedding (vLLM BGE-M3)
    embedding_base_url: str = "http://localhost:8001"
    embedding_api_key: str = "dummy_key"
    embedding_model: str = "embedding-3"
    embedding_dim: int = 1024

    # Neo4j
    neo4j_uri: str = "bolt://localhost:8715"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "aegi-neo4j"

    # Qdrant
    qdrant_url: str = "http://localhost:8716"
    qdrant_grpc_url: str = "localhost:8717"
    qdrant_api_key: str = ""

    # MinIO / S3
    s3_endpoint_url: str = "http://localhost:8711"
    s3_access_key: str = "aegi"
    s3_secret_key: str = "aegi-minio-password"
    s3_bucket: str = "aegi-artifacts"

    # OpenClaw Gateway
    openclaw_gateway_url: str = "ws://localhost:4800"
    openclaw_gateway_token: str = ""

    # SearXNG
    searxng_base_url: str = "http://localhost:8888"

    # 数据库连接池
    db_use_null_pool: bool = False

    # 贝叶斯 ACH
    bayesian_likelihood_support_range: str = "0.55,0.95"
    bayesian_likelihood_contradict_range: str = "0.05,0.45"
    bayesian_update_threshold: float = 0.05

    # 事件驱动推送
    event_push_max_per_hour: int = 10
    event_push_semantic_threshold: float = 0.65
    event_push_expert_collection: str = "expert_profiles"

    # GDELT 数据源
    gdelt_proxy: str = "http://127.0.0.1:7890"
    gdelt_poll_interval_minutes: int = 15
    gdelt_max_articles_per_query: int = 50
    gdelt_auto_ingest: bool = False
    gdelt_anomaly_goldstein_threshold: float = -7.0

    # PyKEEN 链接预测
    pykeen_default_model: str = "RotatE"
    pykeen_embedding_dim: int = 128
    pykeen_num_epochs: int = 100
    pykeen_min_triples: int = 50


settings = Settings()
