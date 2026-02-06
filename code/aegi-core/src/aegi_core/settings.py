# Author: msq
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AEGI_", case_sensitive=False)

    postgres_dsn_async: str = "postgresql+asyncpg://aegi:aegi@localhost:8710/aegi"
    postgres_dsn_sync: str = "postgresql+psycopg://aegi:aegi@localhost:8710/aegi"
    mcp_gateway_base_url: str = "http://localhost:8704"

    # LiteLLM Proxy
    litellm_base_url: str = "http://localhost:8713"
    litellm_api_key: str = "sk-aegi-dev"
    litellm_default_model: str = "default"
    litellm_fast_model: str = "fast"
    litellm_embedding_model: str = "embedding"

    # Local embedding (vLLM BGE-M3)
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

    # MinIO / S3
    s3_endpoint_url: str = "http://localhost:8711"
    s3_access_key: str = "aegi"
    s3_secret_key: str = "aegi-minio-password"
    s3_bucket: str = "aegi-artifacts"


settings = Settings()
