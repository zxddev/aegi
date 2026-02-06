from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AEGI_", case_sensitive=False)

    postgres_dsn_async: str = "postgresql+asyncpg://aegi:aegi@localhost:8710/aegi"
    postgres_dsn_sync: str = "postgresql+psycopg://aegi:aegi@localhost:8710/aegi"
    mcp_gateway_base_url: str = "http://localhost:8704"


settings = Settings()
