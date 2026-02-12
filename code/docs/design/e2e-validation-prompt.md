# AEGI 端到端验证测试（给 Claude Code）

## 任务

验证 AEGI 核心闭环在真实环境中能跑通。不是写单元测试，而是启动真实服务，用真实数据跑一遍完整链路。

**目标：** 证明以下链路可以端到端工作：
```
创建 Case → 创建 Subscription → GDELT 采集 → 发现事件 → Claim 提取 → 贝叶斯 ACH 更新 → 推送通知
```

**输出：** 验证报告保存到 `/home/user/workspace/gitcode/aegi/code/docs/review/2026-02-12/e2e-validation-report.md`

## 在开始前，先阅读

- `src/aegi_core/api/main.py` — app 启动逻辑
- `src/aegi_core/settings.py` — 所有配置项
- `env.sh` — LLM 环境变量
- `src/aegi_core/api/routes/gdelt.py` — GDELT API
- `src/aegi_core/api/routes/bayesian.py` — 贝叶斯 ACH API
- `src/aegi_core/api/routes/subscriptions.py` — 订阅 API

## 环境信息

已在线的服务：
- PostgreSQL: `127.0.0.1:8710`
- Neo4j: `127.0.0.1:8715`
- Qdrant: `127.0.0.1:8716`
- SearXNG: `127.0.0.1:8888`

需要确认/启动的：
- LiteLLM: 配置在 `env.sh`，base_url=`http://localhost:8990`
- AEGI Core API: 需要启动 uvicorn

代理：`http://127.0.0.1:7890`（GDELT API 需要走代理）

## 验证步骤

### Phase 0：环境准备

1. 确认数据库可连接：
```bash
PGPASSWORD=xxx psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "SELECT 1"
```

2. 运行 Alembic migration 确保表结构最新：
```bash
cd /home/user/workspace/gitcode/aegi/code/aegi-core
source .venv/bin/activate
source env.sh
alembic upgrade head
```

3. 确认 LLM 可用（如果 LiteLLM 没跑，尝试直接用 env.sh 里的配置）：
```bash
curl -s http://localhost:8990/v1/models -H "Authorization: Bearer sk-kiro-rs-aegi-local-dev"
```
如果 LiteLLM 不可用，记录下来，跳过需要 LLM 的步骤（claim 提取、贝叶斯评估），但其他步骤仍然要验证。

4. 启动 AEGI Core API（后台运行）：
```bash
cd /home/user/workspace/gitcode/aegi/code/aegi-core
source .venv/bin/activate
source env.sh
export AEGI_GDELT_PROXY="http://127.0.0.1:7890"
uvicorn aegi_core.api.main:create_app --factory --host 0.0.0.0 --port 8700 &
```
等待启动完成，确认 `curl http://localhost:8700/health` 返回 200。

### Phase 1：创建 Case + Subscription

```bash
# 创建一个关于伊朗核问题的 case
curl -s -X POST http://localhost:8700/cases \
  -H "Content-Type: application/json" \
  -d '{"title": "伊朗核谈判动态追踪", "actor_id": "expert_alice", "rationale": "E2E验证测试"}' | jq .

# 记录 case_uid

# 创建订阅
curl -s -X POST http://localhost:8700/subscriptions \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "expert_alice",
    "sub_type": "case",
    "sub_target": "<case_uid>",
    "priority_threshold": 0,
    "event_types": [],
    "match_rules": {"keywords": ["Iran", "nuclear", "伊朗", "核"], "countries": ["IR"]},
    "enabled": true
  }' | jq .
```

### Phase 2：GDELT 手动轮询

```bash
# 手动触发一次 GDELT 轮询
curl -s -X POST http://localhost:8700/gdelt/monitor/poll | jq .

# 检查发现了多少事件
curl -s http://localhost:8700/gdelt/events?limit=10 | jq .

# 查看统计
curl -s http://localhost:8700/gdelt/stats | jq .
```

记录：
- 是否成功连接 GDELT API（走代理）
- 发现了多少事件
- 事件的 title、url、source_domain 是否合理
- matched_subscription_uids 是否正确匹配

### Phase 3：假设初始化 + 贝叶斯 ACH

```bash
# 为 case 生成假设（如果 LLM 可用）
curl -s -X POST http://localhost:8700/cases/<case_uid>/hypotheses/generate \
  -H "Content-Type: application/json" \
  -d '{"actor_id": "expert_alice"}' | jq .

# 如果 LLM 不可用，手动创建假设
# （查看 hypotheses API 的创建端点）

# 初始化先验概率
curl -s -X POST http://localhost:8700/cases/<case_uid>/hypotheses/initialize-priors | jq .

# 查看概率分布
curl -s http://localhost:8700/cases/<case_uid>/hypotheses/probabilities | jq .
```

### Phase 4：手动 Ingest GDELT 事件

```bash
# 选一个 GDELT 事件，手动 ingest 到 case
curl -s -X POST http://localhost:8700/gdelt/events/<event_uid>/ingest \
  -H "Content-Type: application/json" \
  -d '{"case_uid": "<case_uid>"}' | jq .

# 检查是否触发了贝叶斯更新
curl -s http://localhost:8700/cases/<case_uid>/hypotheses/probabilities | jq .
```

### Phase 5：检查事件日志和推送日志

```bash
# 直接查数据库
source env.sh
PGPASSWORD=xxx psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "
  SELECT event_type, status, push_count, created_at 
  FROM event_logs 
  ORDER BY created_at DESC 
  LIMIT 10;
"

PGPASSWORD=xxx psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "
  SELECT user_id, status, match_method, created_at 
  FROM push_logs 
  ORDER BY created_at DESC 
  LIMIT 10;
"
```

### Phase 6：PyKEEN + DoWhy（如果 Neo4j 有数据）

```bash
# 检查 Neo4j 中是否有数据
# 如果有，尝试训练 PyKEEN
curl -s -X POST http://localhost:8700/cases/<case_uid>/links/train \
  -H "Content-Type: application/json" \
  -d '{}' | jq .

# 尝试因果推断（需要足够的数据）
curl -s -X POST http://localhost:8700/cases/<case_uid>/causal/estimate \
  -H "Content-Type: application/json" \
  -d '{"treatment_entity_uid": "...", "outcome_entity_uid": "..."}' | jq .
```

## 验证报告格式

```markdown
# AEGI 端到端验证报告
> 日期：2026-02-12
> 环境：zmkj-new 服务器

## 环境状态
| 服务 | 状态 | 备注 |
|------|------|------|
| PostgreSQL | ✅/❌ | |
| Neo4j | ✅/❌ | |
| Qdrant | ✅/❌ | |
| SearXNG | ✅/❌ | |
| LiteLLM | ✅/❌ | |
| AEGI Core API | ✅/❌ | |

## 链路验证结果
| 步骤 | 状态 | 详情 |
|------|------|------|
| 创建 Case | ✅/❌ | case_uid=... |
| 创建 Subscription | ✅/❌ | |
| GDELT 轮询 | ✅/❌ | 发现 N 个事件 |
| 订阅匹配 | ✅/❌ | |
| 假设生成 | ✅/❌/⏭️ | |
| 贝叶斯更新 | ✅/❌/⏭️ | |
| 事件日志 | ✅/❌ | |
| 推送日志 | ✅/❌ | |
| PyKEEN | ✅/❌/⏭️ | |
| DoWhy | ✅/❌/⏭️ | |

## 发现的问题
（每个问题：描述、严重程度、建议修复方案）

## 结论
（整体评估：哪些链路通了，哪些没通，下一步建议）
```

## 关键约束

- **不修改代码**：这是验证任务，不是开发任务。发现 bug 记录下来，不要当场修
- **记录所有输出**：每个 curl 命令的完整响应都要记录到报告中
- **如果某步失败，继续后面的步骤**：不要因为一步失败就停下来
- **数据库密码**：查看 `env.sh` 或 `settings.py` 中的 `postgres_dsn` 获取
- **GDELT 需要代理**：确保设置了 `AEGI_GDELT_PROXY=http://127.0.0.1:7890`
- **完成后关闭 uvicorn**：验证完成后 kill 后台的 uvicorn 进程
