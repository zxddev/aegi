"""Prometheus 指标收集。

- 请求延迟指标
- Token 使用量指标
- 错误率指标
- 自定义业务指标
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MetricsConfig:
    """指标配置。"""

    enabled: bool = True
    port: int = 9090  # Prometheus 指标端口
    prefix: str = "baize_core"  # 指标前缀


class MetricsManager:
    """指标管理器。"""

    def __init__(self, config: MetricsConfig) -> None:
        """初始化指标管理器。

        Args:
            config: 指标配置
        """
        self._config = config
        self._initialized = False

        # 指标对象
        self._request_latency: Any = None
        self._request_count: Any = None
        self._token_usage: Any = None
        self._tool_calls: Any = None
        self._model_calls: Any = None
        self._error_count: Any = None

    def initialize(self) -> None:
        """初始化 Prometheus 指标。"""
        if not self._config.enabled:
            logger.info("Prometheus 指标已禁用")
            return

        if self._initialized:
            return

        try:
            from prometheus_client import Counter, Histogram, start_http_server

            prefix = self._config.prefix

            # 请求延迟
            self._request_latency = Histogram(
                f"{prefix}_request_latency_seconds",
                "请求延迟（秒）",
                ["endpoint", "method"],
                buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            )

            # 请求计数
            self._request_count = Counter(
                f"{prefix}_request_total",
                "请求总数",
                ["endpoint", "method", "status"],
            )

            # Token 使用量
            self._token_usage = Counter(
                f"{prefix}_token_usage_total",
                "Token 使用总量",
                ["model", "stage"],
            )

            # 工具调用
            self._tool_calls = Counter(
                f"{prefix}_tool_calls_total",
                "工具调用总数",
                ["tool_name", "status"],
            )

            # 模型调用
            self._model_calls = Counter(
                f"{prefix}_model_calls_total",
                "模型调用总数",
                ["model", "stage", "status"],
            )

            # 错误计数
            self._error_count = Counter(
                f"{prefix}_errors_total",
                "错误总数",
                ["error_type", "component"],
            )

            # 启动指标服务器
            start_http_server(self._config.port)

            self._initialized = True
            logger.info("Prometheus 指标服务已启动: port=%d", self._config.port)

        except ImportError as exc:
            logger.warning("prometheus_client 未安装: %s", exc)
        except Exception as exc:
            logger.error("Prometheus 初始化失败: %s", exc)

    # ============ 请求指标 ============

    @contextmanager
    def measure_request(
        self,
        endpoint: str,
        method: str = "POST",
    ) -> Generator[None, None, None]:
        """测量请求延迟。

        Args:
            endpoint: 端点路径
            method: HTTP 方法

        Yields:
            None
        """
        start_time = time.time()
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            if self._request_latency:
                self._request_latency.labels(endpoint=endpoint, method=method).observe(
                    duration
                )
            if self._request_count:
                self._request_count.labels(
                    endpoint=endpoint, method=method, status=status
                ).inc()

    def record_request(
        self,
        endpoint: str,
        method: str,
        status: str,
        duration: float,
    ) -> None:
        """记录请求指标。"""
        if self._request_latency:
            self._request_latency.labels(endpoint=endpoint, method=method).observe(
                duration
            )
        if self._request_count:
            self._request_count.labels(
                endpoint=endpoint, method=method, status=status
            ).inc()

    # ============ Token 指标 ============

    def record_token_usage(
        self,
        model: str,
        stage: str,
        token_count: int,
    ) -> None:
        """记录 Token 使用量。"""
        if self._token_usage:
            self._token_usage.labels(model=model, stage=stage).inc(token_count)

    # ============ 工具调用指标 ============

    def record_tool_call(
        self,
        tool_name: str,
        success: bool,
    ) -> None:
        """记录工具调用。"""
        if self._tool_calls:
            status = "success" if success else "error"
            self._tool_calls.labels(tool_name=tool_name, status=status).inc()

    # ============ 模型调用指标 ============

    def record_model_call(
        self,
        model: str,
        stage: str,
        success: bool,
    ) -> None:
        """记录模型调用。"""
        if self._model_calls:
            status = "success" if success else "error"
            self._model_calls.labels(model=model, stage=stage, status=status).inc()

    # ============ 错误指标 ============

    def record_error(
        self,
        error_type: str,
        component: str,
    ) -> None:
        """记录错误。"""
        if self._error_count:
            self._error_count.labels(error_type=error_type, component=component).inc()


# 全局 MetricsManager 实例
_metrics_manager: MetricsManager | None = None


def get_metrics_config_from_env() -> MetricsConfig:
    """从环境变量获取指标配置。"""
    import os

    return MetricsConfig(
        enabled=os.getenv("PROMETHEUS_ENABLED", "true").lower() == "true",
        port=int(os.getenv("PROMETHEUS_PORT", "9090")),
        prefix=os.getenv("PROMETHEUS_PREFIX", "baize_core"),
    )


def get_metrics_manager() -> MetricsManager:
    """获取全局 MetricsManager。"""
    global _metrics_manager
    if _metrics_manager is None:
        config = get_metrics_config_from_env()
        _metrics_manager = MetricsManager(config)
        _metrics_manager.initialize()
    return _metrics_manager


def add_fastapi_metrics_middleware(app: Any) -> None:
    """为 FastAPI 应用添加指标中间件。

    Args:
        app: FastAPI 应用实例
    """
    try:
        from prometheus_client import make_asgi_app
        from starlette.routing import Mount

        metrics_app = make_asgi_app()
        app.routes.append(Mount("/metrics", metrics_app))
        logger.info("FastAPI 指标端点已添加: /metrics")
    except ImportError:
        logger.warning("prometheus_client 未安装")
    except Exception as exc:
        logger.error("指标中间件添加失败: %s", exc)
