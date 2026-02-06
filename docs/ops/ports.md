# AEGI 端口规划

> 统一使用 87xx 端口段，便于管理和识别（避免与系统/其他项目常用端口冲突）

## 端口分配表

| 端口 | 服务 | 说明 | 状态 |
|------|-----|------|------|
| **8700** | aegi-core | 核心 API 服务 | ✅ |
| **8701** | SearxNG | 元搜索聚合 | ✅ Docker |
| **8702** | ArchiveBox | 网页归档固化 | ✅ Docker |
| **8703** | Unstructured | PDF/文档解析 | ✅ Docker |
| **8704** | aegi-mcp-gateway | MCP Gateway (工具网关) | ✅ |
| **8705** | Firecrawl | 深度抓取 | ✅ Docker |
| **8706** | Perplexica | AI 增强搜索 | ✅ Docker |
| **8707** | OpenSearch | 全文检索/审计日志 | ✅ Docker |
| **8708** | aegi-web | 前端工作台 | 📌 预留 |
| **8709** | - | 预留 | 📌 预留 |

## 其他依赖服务（同属 87xx）

| 端口 | 服务 | 说明 |
|------|-----|------|
| 8710 | PostgreSQL | 关系数据库（docker compose 映射到容器 5432） |
| 8720 | Qdrant HTTP | 向量检索 |
| 8721 | Qdrant gRPC | 向量检索 |
| 8722 | Neo4j Web UI | 图数据库管理界面 |
| 8723 | Neo4j Bolt | 图数据库连接 |
| 8711 | MinIO API | 对象存储（docker compose 映射到容器 9000） |
| 8712 | MinIO Console | 对象存储管理界面（docker compose 映射到容器 9001） |

## 启动命令

### aegi-core (8700)

```bash
cd code/aegi-core
uv sync --dev
uv pip install -e .
uv run uvicorn aegi_core.api.main:app --host 0.0.0.0 --port 8700 --reload
```

### aegi-mcp-gateway (8704)

```bash
cd code/aegi-mcp-gateway
uv sync --dev
uv pip install -e .
uv run uvicorn aegi_mcp_gateway.api.main:app --host 0.0.0.0 --port 8704 --reload
```

## 环境变量

### code/aegi-core/.env

```bash
AEGI_CORE_HOST=0.0.0.0
AEGI_CORE_PORT=8700
AEGI_MCP_GATEWAY_BASE_URL=http://127.0.0.1:8704
```

### code/aegi-mcp-gateway/.env

```bash
MCP_HOST=0.0.0.0
MCP_PORT=8704
```

### repo root `.env` (docker compose)

docker compose 和 aegi-core/aegi-mcp-gateway 的本地默认配置建议共享一份根目录 `.env`：

```bash
POSTGRES_PORT=8710
MINIO_PORT=8711
MINIO_CONSOLE_PORT=8712
AEGI_POSTGRES_DSN_ASYNC=postgresql+asyncpg://aegi:aegi@localhost:8710/aegi
AEGI_POSTGRES_DSN_SYNC=postgresql+psycopg://aegi:aegi@localhost:8710/aegi
AEGI_S3_ENDPOINT_URL=http://localhost:8711
AEGI_MCP_GATEWAY_BASE_URL=http://localhost:8704
```
