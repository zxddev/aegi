# E2E 验证问题排查与修复（给 Claude Code）

## 背景

端到端验证报告（`docs/review/2026-02-12/e2e-validation-report.md`）发现 3 个问题需要解决。

**在开始前，先阅读验证报告了解完整上下文。**

## 问题 1（高优先级）：GDELT 轮询返回 0 事件

### 现象
`POST /gdelt/monitor/poll` 返回 `{"new_events":0,"events":[]}`

### 排查步骤

1. **确认代理可用**：
```bash
curl -x http://127.0.0.1:7890 -sS https://api.gdeltproject.org/api/v2/doc/doc?query=Iran&mode=ArtList&maxrecords=5&timespan=1d&format=json
```
如果代理不通，检查 Clash 是否在运行。

2. **确认 GDELTClient 使用了代理**：
检查 `src/aegi_core/infra/gdelt_client.py` 中 `__init__` 是否正确传递 proxy 给 httpx。
检查 `settings.py` 中 `gdelt_proxy` 的默认值。
检查 `api/routes/gdelt.py` 中 `poll` 端点创建 GDELTClient 时是否传了 proxy。

3. **确认有匹配的订阅**：
```bash
PGPASSWORD='aegi' psql -h 127.0.0.1 -p 8710 -U aegi -d aegi -c "SELECT uid, user_id, match_rules, enabled FROM subscriptions;"
```
如果没有订阅或 match_rules 为空，GDELTMonitor.poll() 会跳过（无关键词可搜）。

4. **确认 poll 逻辑**：
阅读 `src/aegi_core/services/gdelt_monitor.py` 的 `poll()` 方法：
- 它从 Subscription 的 match_rules 中提取 keywords
- 如果没有 keywords，就不会调 GDELT API
- 检查 match_rules 的 JSON 结构是否与代码期望的一致

5. **手动测试 GDELTClient**：
```python
cd /home/user/workspace/gitcode/aegi/code/aegi-core
source .venv/bin/activate
source env.sh
python -c "
import asyncio
from aegi_core.infra.gdelt_client import GDELTClient

async def test():
    client = GDELTClient(proxy='http://127.0.0.1:7890')
    articles = await client.search_articles('Iran nuclear', timespan='1d', max_records=5)
    print(f'Found {len(articles)} articles')
    for a in articles[:3]:
        print(f'  - {a.title[:80]}')
    await client.close()

asyncio.run(test())
"
```

### 修复

根据排查结果修复。最可能的原因：
- A) `api/routes/gdelt.py` 的 poll 端点没有传 proxy 给 GDELTClient
- B) poll() 从 Subscription 提取 keywords 的逻辑与实际 match_rules 结构不匹配
- C) 代理没配置或不可用

修复后重新验证：
```bash
# 启动 AEGI（确保用最新代码）
source env.sh
export AEGI_GDELT_PROXY="http://127.0.0.1:7890"
uvicorn aegi_core.api.main:create_app --factory --port 8720 &

# 确认订阅存在
curl -s http://localhost:8720/subscriptions | jq .

# 重新 poll
curl -s -X POST http://localhost:8720/gdelt/monitor/poll | jq .
```

## 问题 2（中优先级）：假设生成需要先有证据

### 现象
`POST /cases/{case_uid}/hypotheses/generate` 返回 422，要求 `assertion_uids` 和 `source_claim_uids`。

### 分析
这是设计如此——AEGI 的假设生成基于已有证据（assertions/claims），不是凭空生成。但在 E2E 验证场景中，新 case 没有证据，无法生成假设。

### 修复
新增一个 **无证据快速假设生成** 端点或参数，用于冷启动场景：

在 `api/routes/hypotheses.py` 中，修改 `generate` 端点：
- `assertion_uids` 和 `source_claim_uids` 改为 Optional，默认空列表
- 如果两者都为空，改用 case 的 title + rationale 作为上下文让 LLM 生成假设
- 添加一个可选的 `context` 字段，允许用户直接传入文本描述

```python
class HypothesisGenerateRequest(BaseModel):
    assertion_uids: list[str] = []       # 改为 Optional
    source_claim_uids: list[str] = []    # 改为 Optional
    context: str = ""                     # 新增：自由文本上下文
    actor_id: str = ""                    # 保留
```

当 assertion_uids 和 source_claim_uids 都为空时：
- 如果有 context，用 context 作为 LLM 输入
- 如果没有 context，用 case.title + case.rationale 作为 LLM 输入
- LLM prompt 调整为："基于以下背景信息，生成 3-5 个竞争性假设：{context}"

### 验收
```bash
# 无证据生成假设
curl -s -X POST http://localhost:8720/cases/<case_uid>/hypotheses/generate \
  -H "Content-Type: application/json" \
  -d '{"context": "伊朗核谈判最新动态，美国制裁压力下伊朗的可能走向"}' | jq .

# 应返回 3-5 个假设
```

## 问题 3（低优先级）：8700 旧实例路由不一致

### 分析
8700 端口跑的是旧代码，没有新增的路由（subscriptions、gdelt、bayesian、links、causal）。8720 用最新代码启动后全部正常。

### 修复
这不是代码问题，是部署问题。如果 8700 是生产/常驻实例：
```bash
# 找到旧进程
ps aux | grep uvicorn | grep 8700

# 杀掉
kill <pid>

# 用最新代码重启
cd /home/user/workspace/gitcode/aegi/code/aegi-core
source .venv/bin/activate
source env.sh
uvicorn aegi_core.api.main:create_app --factory --host 0.0.0.0 --port 8700
```

如果不需要常驻 8700，忽略此问题。

## 执行顺序

1. 先排查问题 1（GDELT 0 事件），这是阻塞整个 E2E 链路的关键
2. 修复问题 2（假设生成冷启动）
3. 问题 1 和 2 都修复后，重新跑一次完整 E2E 验证，更新报告

## 验收标准

1. `POST /gdelt/monitor/poll` 返回 `new_events > 0`
2. `POST /cases/{case_uid}/hypotheses/generate` 支持无证据生成
3. 重新跑 E2E，至少走通：Case → Subscription → GDELT 发现事件 → 假设生成 → 贝叶斯初始化
4. 现有测试不能 break
