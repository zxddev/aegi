"""应用工厂入口。"""

from fastapi import FastAPI

from baize_mcp_gateway.main import app as _app


def build_app() -> FastAPI:
    """构建 FastAPI 应用。"""
    return _app


app = build_app()
