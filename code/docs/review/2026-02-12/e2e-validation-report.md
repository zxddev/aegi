<!-- Author: msq -->

# AEGI 端到端验证报告
> 日期：2026-02-12
> 环境：本地验证会话（Codex）

## 执行说明
- 按 `code/docs/design/e2e-validation-prompt.md` 的 Phase 0-6 执行。
- 不修改业务代码，仅执行验证命令并记录输出。
- 某步骤失败时继续后续步骤，并在“发现的问题”中记录。

## 环境状态
| 服务 | 状态 | 备注 |
|------|------|------|
| PostgreSQL | ✅ | `127.0.0.1:8710` 可连通，`SELECT 1` 正常 |
| Neo4j | ✅ | `127.0.0.1:8715` TCP 可连通 |
| Qdrant | ✅ | `127.0.0.1:8716` `/collections` 返回 200 |
| SearXNG | ⚠️ | 端口可访问，但 `/search` 返回 403 |
| LiteLLM | ✅ | `http://localhost:8990/v1/models` 返回 200 |
| AEGI Core API | ✅ | `8700` 与 `8720` 的 `/health` 均返回 200 |

## 链路验证结果
| 步骤 | 状态 | 详情 |
|------|------|------|
| 创建 Case | ✅ | 第二轮：`case_1179f15175184f0d9cb03690a3c93545` |
| 创建 Subscription | ✅ | 第二轮：`sub_ebb254b8b7744ff0b2180d33d6afe274` |
| GDELT 轮询 | ⚠️ | 接口可用（200），但 `new_events=0` |
| 订阅匹配 | ⏭️ | 无 GDELT 事件，无法触发匹配 |
| 假设生成 | ⚠️ | 提示文档 payload（`actor_id`）不兼容当前 API（422） |
| 贝叶斯更新 | ⏭️ | 无事件 + 无假设数据，未触发更新 |
| 事件日志 | ✅ | 实际表名为 `event_log`，可查询到记录 |
| 推送日志 | ✅ | 实际表名为 `push_log`，当前 0 行 |
| PyKEEN | ❌ | 三元组不足：`got 0, need at least 50` |
| DoWhy | ❌ | 传入实体不存在：`Treatment entity not found...` |

## 发现的问题
- 高：`8700` 端口实例与当前仓库代码路由不一致（`/subscriptions`、`/gdelt/*`、`/cases/{case_uid}/links/train` 等在 `8700` 为 404），导致首轮验证误判；在隔离实例 `8720` 可复现这些路由存在。
- 中：`e2e-validation-prompt.md` 中假设生成 payload 已过时。当前 `/cases/{case_uid}/hypotheses/generate` 要求 `assertion_uids` 和 `source_claim_uids`，不接受仅 `actor_id`。
- 中：提示文档中的日志表名为 `event_logs/push_logs`，数据库实际为 `event_log/push_log`。
- 中：当前 GDELT 轮询可调用但返回 0 事件，导致“事件发现 → Claim 提取 → 贝叶斯更新 → 推送通知”链路无法在本次环境闭环验证。

## 结论
- 已验证通过：环境连通性、Case 创建、Subscription 创建、GDELT API 可调用、贝叶斯 API 可调用、日志表可查询。
- 未验证通过：GDELT 事件发现后续链路（事件匹配、Claim 提取、贝叶斯更新、推送通知）因 `new_events=0` 无法触发。
- 建议下一步：先解决 GDELT 数据产出（代理/查询条件/时间窗口），并同步更新 `e2e-validation-prompt.md` 的假设接口 payload 与日志表名，再重跑一次完整 E2E。

## 修复后复验（2026-02-12）
- 代码修复范围：
  - `src/aegi_core/infra/gdelt_client.py`：默认 `timespan=1d`、限流重试、非 JSON 响应容错、国家过滤 query 规范化、`aclose` 修复。
  - `src/aegi_core/services/gdelt_monitor.py`：国家字段标准化（避免 `varchar(8)` 溢出）、国家查询不再使用 `*`、DOC 查询显式使用 `settings.gdelt_doc_timespan`。
  - `src/aegi_core/api/routes/hypotheses.py` + `src/aegi_core/services/hypothesis_engine.py`：`/hypotheses/generate` 支持 `actor_id` 冷启动（无证据时使用 case 背景）。
  - `src/aegi_core/services/event_bus.py`：`AegiEvent.case_uid` 支持 `None`，避免空字符串写入 event_log 触发外键错误。

- 关键复验结果（8720 隔离实例）：
  - `POST /gdelt/monitor/poll`：`HTTP 200`，`new_events=135`（之前为 0 或 500）。
  - `POST /cases/{case_uid}/hypotheses/generate` with `{"actor_id":"expert_alice","context":"..."}`：`HTTP 201`，返回 `3` 条假设（之前 422 或空列表）。
  - `POST /cases/{case_uid}/hypotheses/initialize-priors`：`HTTP 200`。

- 测试验证（本地执行）：
  - `uv run pytest tests/test_gdelt_client.py -q` → `9 passed`
  - `uv run pytest tests/test_gdelt_monitor.py -q` → `11 passed`
  - `uv run pytest tests/test_hypothesis_engine_generate.py -q` → `2 passed`
  - `uv run pytest tests/test_push_engine.py -q` → `12 passed`
  - `uv run pytest tests/test_stub_routes_integration.py::TestHypothesesRoutes -q` → `2 passed`

## 执行日志（原始输出）

## Phase 0：环境准备
### PostgreSQL 连通性

```bash
PGPASSWORD='aegi' psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c 'SELECT 1'
```

退出码: 0

```text
 ?column? 
----------
        1
(1 row)
```

### Neo4j 端口检测

```bash
timeout 3 bash -lc '</dev/tcp/127.0.0.1/8715' && echo 'neo4j tcp ok'
```

退出码: 0

```text
neo4j tcp ok
```

### Qdrant 连通性

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' http://127.0.0.1:8716/collections
```

退出码: 0

```text
{"result":{"collections":[{"name":"aegi_chunks"},{"name":"test_chat_1e874a"},{"name":"expert_profiles"},{"name":"test_chat_ab66a1"},{"name":"test_c871d8"},{"name":"test_f53b05"}]},"status":"ok","time":0.000067773}
HTTP_STATUS:200
```

### SearXNG 连通性

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' 'http://127.0.0.1:8888/search?q=iran&format=json'
```

退出码: 0

```text
<!doctype html>
<html lang=en>
<title>403 Forbidden</title>
<h1>Forbidden</h1>
<p>You don&#39;t have the permission to access the requested resource. It is either read-protected or not readable by the server.</p>

HTTP_STATUS:403
```

### Alembic 迁移

```bash
cd '/home/user/workspace/gitcode/aegi/code/aegi-core' && source .venv/bin/activate && source env.sh && alembic upgrade head
```

退出码: 0

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

### LiteLLM 可用性

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' http://localhost:8990/v1/models -H 'Authorization: Bearer sk-kiro-rs-aegi-local-dev'
```

退出码: 0

```text
{"object":"list","data":[{"id":"claude-sonnet-4-5-20250929","object":"model","created":1727568000,"owned_by":"anthropic","display_name":"Claude Sonnet 4.5","type":"chat","max_tokens":32000},{"id":"claude-sonnet-4-5-20250929-thinking","object":"model","created":1727568000,"owned_by":"anthropic","display_name":"Claude Sonnet 4.5 (Thinking)","type":"chat","max_tokens":32000},{"id":"claude-opus-4-5-20251101","object":"model","created":1730419200,"owned_by":"anthropic","display_name":"Claude Opus 4.5","type":"chat","max_tokens":32000},{"id":"claude-opus-4-5-20251101-thinking","object":"model","created":1730419200,"owned_by":"anthropic","display_name":"Claude Opus 4.5 (Thinking)","type":"chat","max_tokens":32000},{"id":"claude-opus-4-6","object":"model","created":1770314400,"owned_by":"anthropic","display_name":"Claude Opus 4.6","type":"chat","max_tokens":32000},{"id":"claude-opus-4-6-thinking","object":"model","created":1770314400,"owned_by":"anthropic","display_name":"Claude Opus 4.6 (Thinking)","type":"chat","max_tokens":32000},{"id":"claude-haiku-4-5-20251001","object":"model","created":1727740800,"owned_by":"anthropic","display_name":"Claude Haiku 4.5","type":"chat","max_tokens":32000},{"id":"claude-haiku-4-5-20251001-thinking","object":"model","created":1727740800,"owned_by":"anthropic","display_name":"Claude Haiku 4.5 (Thinking)","type":"chat","max_tokens":32000}]}
HTTP_STATUS:200
```

### AEGI Core health（启动前）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' http://localhost:8700/health
```

退出码: 0

```text
{"ok":true,"service":"aegi-core"}
HTTP_STATUS:200
```

## Phase 1：创建 Case + Subscription
### 创建 Case

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8700/cases -H 'Content-Type: application/json' --data-binary '@/tmp/aegi-e2e-VcEzGP/create_case.json'
```

退出码: 0

```text
{"case_uid":"case_d7540e97b6dc45bdb7ee6c32c637f521","title":"伊朗核谈判动态追踪","action_uid":"act_e052094ea25f4e7e9e1495d4213ab5e9"}
HTTP_STATUS:201
```

- 解析到 case_uid: case_d7540e97b6dc45bdb7ee6c32c637f521
### 创建 Subscription

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8700/subscriptions -H 'Content-Type: application/json' --data-binary '@/tmp/aegi-e2e-VcEzGP/create_sub.json'
```

退出码: 0

```text
{"type":"urn:aegi:error:http","title":"HTTP error","status":404,"detail":"Not Found","instance":null,"error_code":"http_error","extensions":{"status_code":404}}
HTTP_STATUS:404
```

- 解析到 sub_uid: <未解析到>
## Phase 2：GDELT 手动轮询
### GDELT 手动轮询

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8700/gdelt/monitor/poll
```

退出码: 0

```text
{"type":"urn:aegi:error:http","title":"HTTP error","status":404,"detail":"Not Found","instance":null,"error_code":"http_error","extensions":{"status_code":404}}
HTTP_STATUS:404
```

### 查询 GDELT 事件

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' 'http://localhost:8700/gdelt/events?limit=10'
```

退出码: 0

```text
{"type":"urn:aegi:error:http","title":"HTTP error","status":404,"detail":"Not Found","instance":null,"error_code":"http_error","extensions":{"status_code":404}}
HTTP_STATUS:404
```

- 解析到 event_uid_1: <未解析到>
- 解析到 event_uid_2: <未解析到>
### GDELT 统计

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' http://localhost:8700/gdelt/stats
```

退出码: 0

```text
{"type":"urn:aegi:error:http","title":"HTTP error","status":404,"detail":"Not Found","instance":null,"error_code":"http_error","extensions":{"status_code":404}}
HTTP_STATUS:404
```

## Phase 3：假设初始化 + 贝叶斯 ACH
### 按提示调用假设生成（actor_id）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8700/cases/case_d7540e97b6dc45bdb7ee6c32c637f521/hypotheses/generate -H 'Content-Type: application/json' --data-binary '@/tmp/aegi-e2e-VcEzGP/hyp_generate_prompt_payload.json'
```

退出码: 0

```text
{"type":"urn:aegi:error:validation","title":"Validation error","status":422,"detail":"Validation error","instance":null,"error_code":"validation_error","extensions":{"errors":[{"type":"missing","loc":["body","assertion_uids"],"msg":"Field required","input":{"actor_id":"expert_alice"}},{"type":"missing","loc":["body","source_claim_uids"],"msg":"Field required","input":{"actor_id":"expert_alice"}}]}}
HTTP_STATUS:422
```

### 初始化先验概率（首次）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8700/cases/case_d7540e97b6dc45bdb7ee6c32c637f521/hypotheses/initialize-priors
```

退出码: 0

```text
{"type":"urn:aegi:error:http","title":"HTTP error","status":404,"detail":"Not Found","instance":null,"error_code":"http_error","extensions":{"status_code":404}}
HTTP_STATUS:404
```

### 查看概率分布（首次）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' http://localhost:8700/cases/case_d7540e97b6dc45bdb7ee6c32c637f521/hypotheses/probabilities
```

退出码: 0

```text
{"type":"urn:aegi:error:http","title":"HTTP error","status":404,"detail":"Not Found","instance":null,"error_code":"http_error","extensions":{"status_code":404}}
HTTP_STATUS:404
```

## Phase 4：手动 Ingest GDELT 事件
- 跳过 Phase 4：缺少 case_uid 或 event_uid
## Phase 5：检查事件日志和推送日志
### 查询 event_logs

```bash
PGPASSWORD='aegi' psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "SELECT event_type, status, push_count, created_at FROM event_logs ORDER BY created_at DESC LIMIT 10;"
```

退出码: 1

```text
ERROR:  relation "event_logs" does not exist
LINE 1: ...T event_type, status, push_count, created_at FROM event_logs...
                                                             ^
```

### 查询 push_logs

```bash
PGPASSWORD='aegi' psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "SELECT user_id, status, match_method, created_at FROM push_logs ORDER BY created_at DESC LIMIT 10;"
```

退出码: 1

```text
ERROR:  relation "push_logs" does not exist
LINE 1: ...CT user_id, status, match_method, created_at FROM push_logs ...
                                                             ^
```

## Phase 6：PyKEEN + DoWhy
### PyKEEN 训练

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8700/cases/case_d7540e97b6dc45bdb7ee6c32c637f521/links/train -H 'Content-Type: application/json' -d '{}'
```

退出码: 0

```text
{"type":"urn:aegi:error:http","title":"HTTP error","status":404,"detail":"Not Found","instance":null,"error_code":"http_error","extensions":{"status_code":404}}
HTTP_STATUS:404
```

### DoWhy 因果推断

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8700/cases/case_d7540e97b6dc45bdb7ee6c32c637f521/causal/estimate -H 'Content-Type: application/json' --data-binary '@/tmp/aegi-e2e-VcEzGP/causal_payload.json'
```

退出码: 0

```text
{"type":"urn:aegi:error:http","title":"HTTP error","status":404,"detail":"Not Found","instance":null,"error_code":"http_error","extensions":{"status_code":404}}
HTTP_STATUS:404
```

## 原始执行上下文
- tmp_dir: /tmp/aegi-e2e-VcEzGP
- case_uid: case_d7540e97b6dc45bdb7ee6c32c637f521
- sub_uid: <none>
- event_uid_1: <none>
- event_uid_2: <none>

---

## 第二轮验证（隔离实例 8720）
- 目的：`8700` 存在路由不一致问题，因此使用当前仓库代码在 `8720` 端口重新验证。
- 启动方式：`uvicorn aegi_core.api.main:create_app --factory --port 8720`

### AEGI Core health（8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' http://localhost:8720/health
```

退出码: 0

```text
{"ok":true,"service":"aegi-core"}
HTTP_STATUS:200
```

### 关键路由探测（openapi 过滤）

```bash
curl -sS http://localhost:8720/openapi.json | jq -r '.paths | keys[]' | rg '^/(gdelt|subscriptions|cases/\{case_uid\}/hypotheses|cases/\{case_uid\}/links|cases/\{case_uid\}/causal)' | sort
```

退出码: 0

```text
/cases/{case_uid}/causal/estimate
/cases/{case_uid}/causal/graph
/cases/{case_uid}/hypotheses/bayesian-update
/cases/{case_uid}/hypotheses/diagnosticity
/cases/{case_uid}/hypotheses/generate
/cases/{case_uid}/hypotheses/initialize-priors
/cases/{case_uid}/hypotheses/probabilities
/cases/{case_uid}/hypotheses/recalculate
/cases/{case_uid}/hypotheses/{hypothesis_uid}/explain
/cases/{case_uid}/hypotheses/{hypothesis_uid}/score
/cases/{case_uid}/links/anomalies
/cases/{case_uid}/links/predictions
/cases/{case_uid}/links/predictions/{entity_uid}
/cases/{case_uid}/links/train
/gdelt/events
/gdelt/events/{uid}
/gdelt/events/{uid}/ingest
/gdelt/monitor/poll
/gdelt/monitor/start
/gdelt/monitor/status
/gdelt/monitor/stop
/gdelt/stats
/subscriptions
/subscriptions/{sub_uid}
```

## Phase 1：创建 Case + Subscription（8720）

### 创建 Case（8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8720/cases -H 'Content-Type: application/json' --data-binary '@/tmp/aegi-e2e-8720-BDOHvg/create_case.json'
```

退出码: 0

```text
{"case_uid":"case_1179f15175184f0d9cb03690a3c93545","title":"伊朗核谈判动态追踪-8720","action_uid":"act_fa8ff389b9d242cbacd013a6e2ed4815"}
HTTP_STATUS:201
```

- 解析到 case_uid: case_1179f15175184f0d9cb03690a3c93545
### 创建 Subscription（8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8720/subscriptions -H 'Content-Type: application/json' --data-binary '@/tmp/aegi-e2e-8720-BDOHvg/create_sub.json'
```

退出码: 0

```text
{"uid":"sub_ebb254b8b7744ff0b2180d33d6afe274","user_id":"expert_alice","sub_type":"case","sub_target":"case_1179f15175184f0d9cb03690a3c93545","priority_threshold":0,"event_types":[],"match_rules":{"keywords":["Iran","nuclear","伊朗","核"],"countries":["IR"]},"enabled":true,"interest_text":null,"embedding_synced":false,"created_at":"2026-02-12T03:38:54.021192+00:00","updated_at":"2026-02-12T03:38:54.021209+00:00"}
HTTP_STATUS:200
```

- 解析到 sub_uid: sub_ebb254b8b7744ff0b2180d33d6afe274

## Phase 2：GDELT 手动轮询（8720）

### GDELT 手动轮询（8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8720/gdelt/monitor/poll
```

退出码: 0

```text
{"new_events":0,"events":[]}
HTTP_STATUS:200
```

### 查询 GDELT 事件（8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' 'http://localhost:8720/gdelt/events?limit=10'
```

退出码: 0

```text
{"items":[],"total":0}
HTTP_STATUS:200
```

- 解析到 event_uid_1: <未解析到>
- 解析到 event_uid_2: <未解析到>
### GDELT 统计（8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' http://localhost:8720/gdelt/stats
```

退出码: 0

```text
{"total":0,"by_status":{},"top_countries":[],"by_day":[]}
HTTP_STATUS:200
```


## Phase 3：假设初始化 + 贝叶斯 ACH（8720）

### 按提示调用假设生成（actor_id，8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8720/cases/case_1179f15175184f0d9cb03690a3c93545/hypotheses/generate -H 'Content-Type: application/json' --data-binary '@/tmp/aegi-e2e-8720-BDOHvg/hyp_prompt_payload.json'
```

退出码: 0

```text
{"type":"urn:aegi:error:validation","title":"Validation error","status":422,"detail":"Validation error","instance":null,"error_code":"validation_error","extensions":{"errors":[{"type":"missing","loc":["body","assertion_uids"],"msg":"Field required","input":{"actor_id":"expert_alice"}},{"type":"missing","loc":["body","source_claim_uids"],"msg":"Field required","input":{"actor_id":"expert_alice"}}]}}
HTTP_STATUS:422
```

### 初始化先验概率（首次，8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8720/cases/case_1179f15175184f0d9cb03690a3c93545/hypotheses/initialize-priors
```

退出码: 0

```text
{"priors":{}}
HTTP_STATUS:200
```

### 查看概率分布（首次，8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' http://localhost:8720/cases/case_1179f15175184f0d9cb03690a3c93545/hypotheses/probabilities
```

退出码: 0

```text
{"case_uid":"case_1179f15175184f0d9cb03690a3c93545","hypotheses":[],"total_evidence_assessed":0,"last_updated":null}
HTTP_STATUS:200
```


## Phase 4：手动 Ingest GDELT 事件（8720）

- 跳过 Phase 4：缺少 case_uid 或 event_uid

## Phase 5：事件日志和推送日志（8720）

### 按提示查询 event_logs（8720）

```bash
PGPASSWORD='aegi' psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "SELECT event_type, status, push_count, created_at FROM event_logs ORDER BY created_at DESC LIMIT 10;"
```

退出码: 1

```text
ERROR:  relation "event_logs" does not exist
LINE 1: ...T event_type, status, push_count, created_at FROM event_logs...
                                                             ^
```

### 按提示查询 push_logs（8720）

```bash
PGPASSWORD='aegi' psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "SELECT user_id, status, match_method, created_at FROM push_logs ORDER BY created_at DESC LIMIT 10;"
```

退出码: 1

```text
ERROR:  relation "push_logs" does not exist
LINE 1: ...CT user_id, status, match_method, created_at FROM push_logs ...
                                                             ^
```

### 发现日志相关表（8720）

```bash
PGPASSWORD='aegi' psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name ILIKE '%event%' OR table_name ILIKE '%push%' ORDER BY table_name;"
```

退出码: 0

```text
  table_name  
--------------
 event_log
 gdelt_events
 push_log
(3 rows)
```

### 查询 event_log（若存在）

```bash
PGPASSWORD='aegi' psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "SELECT event_type, status, push_count, created_at FROM event_log ORDER BY created_at DESC LIMIT 10;"
```

退出码: 0

```text
     event_type     | status | push_count |          created_at           
--------------------+--------+------------+-------------------------------
 pipeline.completed | done   |          0 | 2026-02-12 03:07:32.679005+00
(1 row)
```

### 查询 push_log（若存在）

```bash
PGPASSWORD='aegi' psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "SELECT user_id, status, match_method, created_at FROM push_log ORDER BY created_at DESC LIMIT 10;"
```

退出码: 0

```text
 user_id | status | match_method | created_at 
---------+--------+--------------+------------
(0 rows)
```


## Phase 6：PyKEEN + DoWhy（8720）

### PyKEEN 训练（8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8720/cases/case_1179f15175184f0d9cb03690a3c93545/links/train -H 'Content-Type: application/json' -d '{}'
```

退出码: 0

```text
{"type":"urn:aegi:error:http","title":"HTTP error","status":400,"detail":"Not enough triples for training: got 0, need at least 50.","instance":null,"error_code":"http_error","extensions":{"status_code":400}}
HTTP_STATUS:400
```

### DoWhy 因果推断（8720）

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' -X POST http://localhost:8720/cases/case_1179f15175184f0d9cb03690a3c93545/causal/estimate -H 'Content-Type: application/json' --data-binary '@/tmp/aegi-e2e-8720-BDOHvg/causal_payload.json'
```

退出码: 0

```text
{"type":"urn:aegi:error:http","title":"HTTP error","status":400,"detail":"Treatment entity not found in case graph: ent_placeholder_treatment","instance":null,"error_code":"http_error","extensions":{"status_code":400}}
HTTP_STATUS:400
```


## 第二轮执行上下文
- api_base: http://localhost:8720
- tmp_dir: /tmp/aegi-e2e-8720-BDOHvg
- case_uid: case_1179f15175184f0d9cb03690a3c93545
- sub_uid: sub_ebb254b8b7744ff0b2180d33d6afe274
- event_uid_1: <none>
- event_uid_2: <none>
- cleanup: 已停止隔离实例 uvicorn（pid 64986）
