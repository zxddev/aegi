"""配置加载隔离测试。

验证 BAIZE_CORE_SKIP_DOTENV 功能和配置延迟加载。
"""

from __future__ import annotations

import os
from unittest import mock

import pytest


class TestSettingsSkipDotenv:
    """测试 BAIZE_CORE_SKIP_DOTENV 功能。"""

    def test_skip_dotenv_with_true(self) -> None:
        """BAIZE_CORE_SKIP_DOTENV=true 时跳过 .env 加载。"""
        # 重置模块状态
        from baize_core.config import settings

        settings.reset_settings()

        # 设置跳过标记
        with mock.patch.dict(os.environ, {"BAIZE_CORE_SKIP_DOTENV": "true"}):
            # 调用 _load_env_if_needed 应该跳过加载
            settings._load_env_if_needed()
            assert settings._ENV_LOADED is True

        # 清理
        settings.reset_settings()

    def test_skip_dotenv_with_yes(self) -> None:
        """BAIZE_CORE_SKIP_DOTENV=yes 时跳过 .env 加载。"""
        from baize_core.config import settings

        settings.reset_settings()

        with mock.patch.dict(os.environ, {"BAIZE_CORE_SKIP_DOTENV": "yes"}):
            settings._load_env_if_needed()
            assert settings._ENV_LOADED is True

        settings.reset_settings()

    def test_skip_dotenv_with_1(self) -> None:
        """BAIZE_CORE_SKIP_DOTENV=1 时跳过 .env 加载。"""
        from baize_core.config import settings

        settings.reset_settings()

        with mock.patch.dict(os.environ, {"BAIZE_CORE_SKIP_DOTENV": "1"}):
            settings._load_env_if_needed()
            assert settings._ENV_LOADED is True

        settings.reset_settings()


class TestSettingsReset:
    """测试配置重置功能。"""

    def test_reset_clears_cache(self) -> None:
        """reset_settings 应清除缓存。"""
        from baize_core.config import settings

        # 先设置一些状态
        settings._ENV_LOADED = True
        settings._SETTINGS = object()  # 模拟已加载的配置

        # 重置
        settings.reset_settings()

        # 验证状态已清除
        assert settings._SETTINGS is None
        assert settings._ENV_LOADED is False


class TestSettingsLazyLoad:
    """测试配置延迟加载。"""

    def test_env_not_loaded_on_import(self) -> None:
        """导入模块时不应自动加载 .env。"""
        from baize_core.config import settings

        # 重置状态
        settings.reset_settings()

        # 验证未加载
        assert settings._ENV_LOADED is False

    def test_env_loaded_on_get_settings(self) -> None:
        """调用 get_settings 时应加载 .env。"""
        from baize_core.config import settings

        settings.reset_settings()

        # 在跳过模式下调用（避免真实加载）
        with mock.patch.dict(os.environ, {"BAIZE_CORE_SKIP_DOTENV": "true"}):
            # 需要提供必要的环境变量
            test_env = {
                "BAIZE_CORE_SKIP_DOTENV": "true",
                "POSTGRES_DSN": "postgresql://test:test@localhost/test",
                "MINIO_ENDPOINT": "localhost:9000",
                "MINIO_ACCESS_KEY": "test",
                "MINIO_SECRET_KEY": "test",
                "MINIO_SECURE": "false",
                "MINIO_BUCKET": "test",
                "MCP_BASE_URL": "http://localhost:8080",
                "MCP_API_KEY": "test",
                "MCP_TLS_VERIFY": "false",
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USER": "neo4j",
                "NEO4J_PASSWORD": "test",
                "QDRANT_URL": "http://localhost:6333",
                "QDRANT_GRPC_URL": "http://localhost:6334",
                "DEFAULT_LLM_PROVIDER": "openai",
                "DEFAULT_MODEL": "gpt-4",
            }
            with mock.patch.dict(os.environ, test_env, clear=False):
                try:
                    config = settings.get_settings()
                    assert settings._ENV_LOADED is True
                    assert config is not None
                except ValueError:
                    # 如果缺少某些必要的环境变量，这是预期的
                    # 重要的是 _load_env_if_needed 被调用了
                    assert settings._ENV_LOADED is True

        settings.reset_settings()
