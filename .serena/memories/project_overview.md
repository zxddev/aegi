# aegi 项目概览

## 用途
Documentation-first 情报分析工作区，包含核心分析引擎和 MCP 网关。

## 技术栈
- Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic
- 基础设施: PostgreSQL (asyncpg), Neo4j, Qdrant, MinIO
- 依赖管理: uv
- Lint/Format: ruff (line-length=100)
- 测试: pytest + pytest-asyncio (asyncio_mode=auto)

## 代码结构
- `code/aegi-core/` — 核心引擎 (services, api, db, contracts, infra, regression)
- `code/aegi-mcp-gateway/` — MCP 工具网关 (policy, audit, api)
- `docs/` — 文档 (foundry, v0.3, ops, archive)
- `openspec/` — OpenSpec 工件

## 关键模块 (aegi-core)
- `services/` — 业务逻辑 (claim_extractor, hypothesis_engine, kg_mapper, causal_reasoner, etc.)
- `api/routes/` — REST 路由 (cases, evidence, hypotheses, kg, chat, etc.)
- `db/models/` — ORM 模型 (case, evidence, hypothesis, assertion, etc.)
- `contracts/` — 契约 (schemas, errors, audit, llm_governance)
- `infra/` — 基础设施客户端 (neo4j, qdrant, minio, llm_client)
- `regression/` — 回归测试指标与报告
