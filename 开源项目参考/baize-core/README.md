# baize-core

防务 OSINT 深度研究后端（Phase 0）。目标是先打通证据链、策略闸门与审计回放的最小闭环，作为后续工作台与高级能力的稳定基础。

## 运行方式（开发）

```bash
python -m alembic upgrade head
uvicorn baize_core.api.main:app --reload --port 8000
```

## 环境准备（Python 3.12）

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## 虚拟环境要求

- 运行与测试必须在项目虚拟环境中执行（`.venv`）。
- 禁止直接在系统 Python 上安装依赖。

示例：

```bash
. .venv/bin/activate
python -m alembic upgrade head
python -m pytest tests/test_storm_e2e.py
```

可选安装 Deep Agents 依赖：

```bash
pip install -e ".[full]"
```

## 环境变量

- `BAIZE_CORE_ENV`：运行环境（默认 `dev`）
- `BAIZE_CORE_ALLOWED_MODELS`：允许的模型列表（逗号分隔，默认空）
- `BAIZE_CORE_ALLOWED_TOOLS`：允许的工具列表（逗号分隔，默认空）
- `BAIZE_CORE_POLICY_DEFAULT_ALLOW`：是否默认放行（默认 `false`）
- `BAIZE_CORE_TOOL_TIMEOUT_MS`：工具超时上限（毫秒，默认 `30000`）
- `BAIZE_CORE_TOOL_MAX_PAGES`：工具最大页数上限（默认 `20`）
- `BAIZE_CORE_MAX_ITERATIONS`：深度迭代次数上限（默认 `3`）
- `BAIZE_CORE_MIN_SOURCES`：最小来源数要求（默认 `3`）
- `BAIZE_CORE_MAX_CONCURRENCY`：工具并发上限（默认 `5`）
- `BAIZE_CORE_REQUIRE_ARCHIVE_FIRST`：是否强制 Archive-First（默认 `true`）
- `BAIZE_CORE_REQUIRE_CITATIONS`：是否强制引用（默认 `true`）
- `BAIZE_CORE_HITL_RISK_LEVELS`：触发人工复核的风险等级（逗号分隔，默认 `high`）
- `BAIZE_CORE_TOOL_RISK_LEVELS`：工具风险等级映射（格式 `tool:level`，逗号分隔，默认 `web_crawl:high,archive_url:high`）
- `BAIZE_CORE_AUDIT_LOG`：审计日志路径（默认 `output/baize_core_audit.jsonl`）
- `POSTGRES_DSN`：数据库连接串（必须）
- `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_SECURE` / `MINIO_BUCKET`：MinIO 配置（必须）
- `MCP_BASE_URL` / `MCP_API_KEY`：MCP Gateway 配置（必须）
- `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`：Neo4j 配置（必须）
- `QDRANT_URL` / `QDRANT_GRPC_URL` / `QDRANT_API_KEY`：Qdrant 配置（必须）

## 数据库说明

- 使用 schema `baize_core` 隔离表名，避免与现有库冲突。

## LangGraph / Deep Agents

- LangGraph 用于编排审查子图与 OODA 子图（缺少依赖时自动降级为直连审查）。
- Deep Agents 作为可选运行器入口（仅作 CLI/skills/middleware，不替代编排主线）。

## 主要接口

- `GET /health`：健康检查
- `POST /tasks`：创建任务
- `POST /reports/export`：证据链审查（可选 OODA）
- `POST /artifacts`：上传 Artifact 到 MinIO 并落库
- `POST /reviews`：创建 HITL 审查
- `GET /reviews/{review_id}`：查询审查状态
- `POST /reviews/{review_id}/approve`：通过审查
- `POST /reviews/{review_id}/reject`：拒绝审查
- `POST /toolchain/ingest`：运行 MCP 工具链并落库证据链
- `POST /entities` / `GET /entities`：写入/查询实体
- `POST /events` / `GET /events`：写入/查询事件

## CLI

```bash
baize-core toolchain-ingest --task-id task_demo --query "东亚海上联合演习"
baize-core entities-add ./entities.json
baize-core events-add ./events.json
```

## MCP 工具链示例

```bash
curl -X POST "http://localhost:8000/toolchain/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_demo",
    "query": "东亚海上联合演习",
    "max_results": 5,
    "language": "zh",
    "time_range": "30d",
    "max_depth": 1,
    "max_pages": 5,
    "obey_robots_txt": true,
    "timeout_ms": 30000,
    "chunk_size": 800,
    "chunk_overlap": 120
  }'
```

返回结果包含 `artifact_uids`、`chunk_uids`、`evidence_uids`，可用于后续实体/事件写入。

## 目录结构

```
baize_core/
  api/            # HTTP 接口与请求校验
  orchestration/  # LangGraph 主线编排
  policy/         # 策略引擎（deny-by-default）
  evidence/       # 证据链模型与引用完整性校验
  storage/        # 数据访问与持久化适配
  tools/          # 工具接入与审计包装
  audit/          # ToolTrace / PolicyDecision 记录
  schemas/        # 结构化契约（Pydantic）
  config/         # 配置加载
```
