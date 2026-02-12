# 审查报告 03：MCP Gateway 与 aegi-core 协作

> 审查日期：2026-02-11
> 审查范围：`code/aegi-mcp-gateway/src/` 全部代码 + `code/aegi-core/` 中 tool 相关服务

---

## 一、架构关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                        aegi-core (:8700)                        │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐   │
│  │ API Routes   │    │ Tool Service Layer                   │   │
│  │              │    │                                      │   │
│  │ /artifacts   │───>│ tool_archive_service.py              │   │
│  │ /evidence    │───>│ tool_search_service.py               │   │
│  │ /pipelines   │───>│ tool_parse_service.py                │   │
│  │              │    │                                      │   │
│  │              │    │  ┌─────────┐  ┌──────────┐           │   │
│  │              │    │  │ Action  │  │ToolTrace │  ← PG     │   │
│  │              │    │  └─────────┘  └──────────┘           │   │
│  └──────────────┘    └──────────┬───────────────────────────┘   │
│                                 │ HTTP (httpx)                  │
│  ┌──────────────┐               │                               │
│  │ openclaw/    │               │                               │
│  │ tools.py     │  ← 反向调用   │                               │
│  │ (OpenClaw    │    (无ToolTrace)                              │
│  │  Agent入口)  │               │                               │
│  └──────────────┘               │                               │
└─────────────────────────────────┼───────────────────────────────┘
                                  │
                    POST /tools/* │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    aegi-mcp-gateway (:8704)                      │
│                                                                 │
│  ┌────────────┐   ┌──────────┐   ┌──────────────────────────┐  │
│  │ policy.py  │   │ errors.py│   │ audit/tool_trace.py      │  │
│  │ 域名白名单 │   │ 统一错误 │   │ 内存 + JSONL 审计日志    │  │
│  │ 频率限制   │   │ 信封格式 │   └──────────────────────────┘  │
│  └─────┬──────┘   └──────────┘                                  │
│        │                                                        │
│  ┌─────┴──────────────────────────────────────────────────────┐ │
│  │ POST /tools/meta_search  ──→ SearXNG (:8888)              │ │
│  │ POST /tools/archive_url  ──→ ArchiveBox (docker exec)     │ │
│  │ POST /tools/doc_parse    ──→ Unstructured API (:8703)     │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**数据流方向：**

- **正向**：aegi-core API Route → Tool Service → ToolClient (httpx) → MCP Gateway → 外部服务
- **反向**：OpenClaw Agent → `openclaw/tools.py` → aegi-core 内部服务（不经过 Gateway）

---

## 二、接口清单

### 2.1 aegi-core → MCP Gateway（ToolClient HTTP 调用）

| 方法 | 端点 | 请求体 | 成功响应 | 策略检查 |
|---|---|---|---|---|
| `archive_url` | `POST /tools/archive_url` | `{url}` | `{ok, tool, url, archived, snapshot, policy}` | 域名白名单 + 频率限制 |
| `meta_search` | `POST /tools/meta_search` | `{q, categories?, language?, safesearch?}` | `{ok, tool, results, q}` | 无 |
| `doc_parse` | `POST /tools/doc_parse` | `{artifact_version_uid, file_url}` | `{ok, tool, artifact_version_uid, chunks}` | 无 |

统一错误信封：`{error_code, message, details}` — HTTP 400 / 403 / 429 / 5xx

### 2.2 aegi-core 内部 Read API

| 端点 | 说明 |
|---|---|
| `GET /tool_traces/{uid}` | 返回完整 ToolTrace 记录（裸 dict，无 Pydantic schema） |

### 2.3 OpenClaw Agent → aegi-core（反向调用，`/openclaw/tools/`）

| 端点 | 说明 |
|---|---|
| `POST /submit_evidence` | 提交证据（创建 Artifact → Version → Chunk → Evidence，嵌入 Qdrant） |
| `POST /create_case` | 创建案例 |
| `POST /query_kg` | 查询知识图谱（Neo4j + Qdrant 语义搜索） |
| `POST /run_pipeline` | 运行分析管线（自动提取 claims → 执行 playbook） |
| `POST /get_report` | 获取报告摘要（统计 evidence/claims/assertions/hypotheses） |
| `POST /dispatch_research` | 分发研究任务到 OpenClaw |
| `POST /notify_user` | 通知用户 |
| `GET /playbooks` | 列出可用 playbook |
| `GET /stages` | 列出 pipeline stages |

### 2.4 MCP Gateway 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `AEGI_GATEWAY_ALLOW_DOMAINS` | 空（允许全部） | CSV 域名白名单 |
| `AEGI_GATEWAY_MIN_INTERVAL_MS` | `0`（禁用） | per-tool-per-domain 频率限制间隔 |
| `AEGI_GATEWAY_CACHE_ENABLED` | `0` | 缓存开关（仅元数据，无实现） |
| `AEGI_GATEWAY_CACHE_TTL_S` | `60` | 缓存 TTL（仅元数据，无实现） |
| `AEGI_SEARXNG_BASE_URL` | `http://localhost:8701` | SearXNG 地址 |
| `AEGI_UNSTRUCTURED_BASE_URL` | `http://localhost:8703` | Unstructured API 地址 |
| `AEGI_ARCHIVEBOX_CONTAINER` | `archivebox` | ArchiveBox Docker 容器名 |
| `AEGI_GATEWAY_TRACE_DIR` | 未设置 | JSONL 审计日志目录 |

---

## 三、逐项审查

### 3.1 MCP Gateway 的职责边界

Gateway 是一个纯 HTTP 代理层，职责三项：

1. **出站策略执行** — 域名白名单 + per-tool-per-domain 频率限制（仅 `archive_url` 生效）
2. **统一错误格式化** — 所有错误转为 `{error_code, message, details}` 信封
3. **本地审计日志** — 内存 `TOOL_TRACES` 列表 + 可选 JSONL 文件持久化

代理了 3 个外部工具：

| 工具 | 后端服务 | 调用方式 |
|---|---|---|
| `meta_search` | SearXNG | HTTP GET |
| `archive_url` | ArchiveBox | `docker exec` shell 命令 |
| `doc_parse` | Unstructured API | HTTP POST（先下载文件再转发） |

### 3.2 调用方式与接口契约

**协议**：纯 HTTP/REST（JSON over HTTP）。尽管名为 "MCP Gateway"，未实现任何 MCP (Model Context Protocol) 协议，无 stdio/SSE transport，无 MCP SDK 依赖。

**Core 端调用链**：

```
API Route
  → tool_*_service.py (创建 Action, 记录 ToolTrace)
    → ToolClient._post() (httpx, 30s 超时, 3 次重试 + 指数退避)
      → POST http://localhost:8704/tools/*
```

**契约清晰度**：

- 成功响应格式在 Gateway 端硬编码，Core 端 `ToolClient._post()` 做 JSON 解析 + `duration_ms` 注入
- 错误信封 `{error_code, message, details}` 两端一致，Core 端精确匹配此 shape 决定是否抛 `AegiHTTPError`
- 请求/响应模型分别在两个项目中独立定义（Gateway 用 Pydantic model，Core 用 dict），**无共享契约包**

### 3.3 Tool Trace 完整性

**双层审计架构**：

| 层 | 存储 | 内容 |
|---|---|---|
| Gateway | 内存 + JSONL | `{tool_name, request, response, status, duration_ms, error, policy}` |
| Core | PostgreSQL `actions` + `tool_traces` | 完整审计：who/why/what (Action) + how/result (ToolTrace) |

**ToolTrace 模型字段**（PostgreSQL `tool_traces` 表）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `uid` | String(64), PK | 格式 `tt_{uuid4().hex}` |
| `case_uid` | FK → cases.uid | 所属案例 |
| `action_uid` | FK → actions.uid | 父级 Action |
| `tool_name` | String(128) | 工具名（`archive_url` / `meta_search` / `doc_parse` / `pipeline.*`） |
| `request` | JSONB | 发送到 Gateway 的请求 |
| `response` | JSONB | 收到的响应（或错误详情） |
| `status` | String(32) | `ok` / `denied` / `error` / `unknown` |
| `duration_ms` | Integer | 调用耗时 |
| `error` | Text | 错误码（`policy_denied` / `rate_limited` / `gateway_error`） |
| `policy` | JSONB | 策略决策元数据 |
| `trace_id` / `span_id` | String(64) | 分布式追踪 ID（已预留，未使用） |

**记录生命周期**（三个 tool service 统一模式）：

1. 校验 case 存在
2. 创建 `Action` 记录（`action_type="tool.{name}"`），flush 获取 FK
3. 启动 monotonic 计时器，生成 `tool_trace_uid`
4. 调用 `ToolClient` 方法
5. 成功：创建 `ToolTrace(status="ok")`，`doc_parse` 额外创建 `Chunk` + `Evidence` 记录
6. 失败：创建 `ToolTrace(status="denied"|"error")`，记录错误详情，re-raise
7. 更新 `Action.outputs`，commit

**可追溯性**：通过 `GET /tool_traces/{uid}` 可查询完整输入输出。`Action` 记录 who/why/what，`ToolTrace` 记录 how/result。

### 3.4 职责重叠与循环依赖

**无循环依赖** — 依赖方向单一：`aegi-core → MCP Gateway`（HTTP）。`openclaw/tools.py` 是反向入口（外部 Agent → aegi-core），不经过 Gateway。

**依赖图**：

```
openclaw/tools.py  (独立 — OpenClaw Agent → AEGI 端点)
    依赖: case_service, ingest_helpers, PipelineOrchestrator, LLMClient, Neo4jStore, QdrantStore
    不使用 ToolClient 或 ToolTrace

tool_client.py  (HTTP 客户端 → MCP Gateway)
    依赖: httpx, AegiHTTPError

tool_parse_service.py  ───┐
tool_search_service.py  ──┼──→ 均依赖: ToolClient, ToolTrace, Action, Case
tool_archive_service.py ──┘

tool_parse_service.py 额外依赖: Chunk, Evidence（从解析结果创建 DB 记录）
```

### 3.5 鉴权、限流、错误处理

| 机制 | 状态 | 详情 |
|---|---|---|
| 鉴权 | **无** | Gateway 无任何 auth 中间件，任何能访问 :8704 的客户端均可调用 |
| 限流 | **部分** | 仅 `archive_url` 有 per-tool-per-domain 内存限流，其余两个工具无限流 |
| 域名白名单 | **部分** | 仅 `archive_url` 执行 `evaluate_outbound_url()`，其余不检查 |
| 错误处理 | **完整** | 统一错误信封（400/403/429），Core 端 3 次重试 + 指数退避（0.5s, 1s） |
| robots.txt | **未实现** | 已预留字段，stub 返回 `p0_fixtures_only` |
| 缓存 | **未实现** | Settings 有 `cache_enabled`/`cache_ttl_s` 字段但无实际逻辑 |

---

## 四、测试覆盖

### 4.1 Core 端测试

| 测试文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `test_tool_trace_recording.py` | 4 | Happy path + 三种错误模式（denied/rate_limited/gateway_error） |
| `test_tool_trace_read_api.py` | 1 | `GET /tool_traces/{uid}` 返回字段完整性 |
| `test_tool_trace_gateway_integration.py` | 1 | 真实 Gateway（ASGI transport）端到端策略验证 |

测试使用 `app.dependency_overrides` 注入 Fake ToolClient，集成测试通过 `httpx.ASGITransport` 将真实 Gateway 嵌入进程内。

### 4.2 Gateway 端测试

| 测试文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `test_tools_contract.py` | 5 | 三个工具的成功响应格式 + 域名拒绝 + 缺少 file_url 校验 |
| `test_health.py` | 1 | 健康检查端点 |
| `test_gateway_policy_and_trace.py` | — | 策略引擎 + 审计日志 |

---

## 五、问题清单

### P0 — 安全风险

| # | 问题 | 位置 | 影响 | 建议 |
|---|---|---|---|---|
| 1 | **Gateway 无鉴权** | `api/main.py` | 任何能访问 :8704 的客户端可调用所有工具 | 添加 API Key 或内部 mTLS |
| 2 | **`_auto_extract_claims` 绕过 LLMClient** | `openclaw/tools.py` | 直接 httpx 调 LLM API，绕过 token tracking 和错误处理 | 改用 `LLMClient.invoke()` |

### P1 — 架构缺陷

| # | 问题 | 位置 | 影响 | 建议 |
|---|---|---|---|---|
| 3 | **策略执行不一致** | `routes/tools.py` | `meta_search` 和 `doc_parse` 不经过策略引擎 | 统一走 `evaluate_outbound_url()` |
| 4 | **无共享契约包** | 两个项目 | 请求/响应模型独立定义，一端改字段另一端不会报错 | 抽取共享 schema 包或 OpenAPI spec |
| 5 | **双层审计无关联** | Gateway JSONL + Core PG | 同一次调用产生两份审计记录但无法关联 | 使用 `trace_id`/`span_id` 贯穿两层 |
| 6 | **OpenClaw 端点无审计** | `openclaw/tools.py` 全部 9 个端点 | 外部 Agent 调用完全无 ToolTrace 记录 | 补齐 Action + ToolTrace 记录 |
| 7 | **名不副实** | 项目命名 | 叫 "MCP Gateway" 但未实现 MCP 协议 | 重命名为 `tool-gateway` 或实现 MCP transport |

### P2 — 代码质量

| # | 问题 | 位置 | 影响 | 建议 |
|---|---|---|---|---|
| 8 | **ToolTrace 无 Pydantic schema** | `GET /tool_traces/{uid}` | 返回裸 dict，无类型保证，API 文档不完整 | 添加 `ToolTraceResponse` schema |
| 9 | **Pipeline stage trace 是 best-effort** | `orchestration.py` | try/except 包裹，失败静默回滚，可能丢失审计 | 改为必须成功或单独事务 |
| 10 | **缓存配置未实现** | `settings.py` | `cache_enabled`/`cache_ttl_s` 有字段无逻辑，误导使用者 | 实现缓存或移除配置项 |
| 11 | **robots.txt 未实现** | `policy.py` | stub 返回 `p0_fixtures_only`，`PolicyDecision.robots` 永远为空 | 实现或标记为 TODO |
| 12 | **SearXNG 端口不一致** | `settings.py` 默认 8701 | 实际 SearXNG 运行在 8888（Phase 4 已修复 Core 端，Gateway 端未同步） | 更新默认值为 8888 |

---

## 六、改进优先级建议

```
立即修复（P0）:
  #1 Gateway 鉴权 → API Key middleware
  #2 _auto_extract_claims → 走 LLMClient

短期改进（P1）:
  #3 统一策略执行
  #5 trace_id 贯穿双层审计
  #6 OpenClaw 端点补齐审计

中期优化（P2）:
  #4 共享契约包
  #7 项目重命名或实现 MCP
  #8 ToolTrace Pydantic schema
  #9 Pipeline trace 事务保证
```
