# CC 任务：P2 InvestigationAgent 最小闭环

## 背景

AEGI 的自主搜集闭环差最后一段：`hypothesis.updated` 事件已经能发出，但没有监听器去触发自动调研。需要补上这个闭环，让 AEGI 能自主发现信息缺口并主动搜集验证。

## 现状（已有的）

- `bayesian_ach.py` 的 `create_bayesian_update_handler` 在贝叶斯更新后会 emit `hypothesis.updated` 事件
- `bayesian_ach.py` 的 `get_evidence_gaps()` 能识别哪些假设对缺乏区分性证据
- `dispatch.py` 的 `dispatch_research(query, case_uid, user_id)` 能把调研任务派发给 OpenClaw agent
- `dispatch.py` 的 `notify_user(user_id, message)` 能往用户会话注入通知
- `openclaw/tools.py` 有 `aegi_submit_evidence` 端点，agent 可以回写证据
- `api/main.py` 启动时注册了 push_handler（监听所有事件）和 bayesian_handler（监听 `claim.extracted`）

## 缺失的（需要实现）

### 任务 1：InvestigationHandler — 监听 hypothesis.updated 触发自动调研

新建 `src/aegi_core/services/investigation_agent.py`：

```python
"""自主调研代理 — 监听假设变化，识别信息缺口，主动搜集验证。

闭环：hypothesis.updated → 识别 evidence_gap → 生成搜索策略 → 执行搜索 →
      结果进入 pipeline → claim.extracted → 贝叶斯更新 → 循环
"""

class InvestigationConfig:
    """调研配置，所有阈值可通过 settings 配置。"""
    max_rounds: int = 3                    # 单次触发最大搜索轮次
    min_posterior_diff: float = 0.15       # 后验差值低于此值才触发调研
    min_change_threshold: float = 0.05     # hypothesis.updated 的 max_change 超过此值才触发
    cooldown_seconds: int = 300            # 同一 case 的调研冷却时间
    max_concurrent_investigations: int = 3 # 最大并发调研数
    token_budget_per_round: int = 10000    # 每轮 token 预算
    search_sources: list[str] = ["searxng", "gdelt"]  # 搜索源

class InvestigationRound:
    """单轮调研记录。"""
    round_number: int
    gap_description: str
    search_queries: list[str]
    results_count: int
    claims_extracted: int
    posterior_change: float  # 本轮搜索后假设概率变化
    
class InvestigationResult:
    """完整调研结果。"""
    case_uid: str
    trigger_event: str  # 触发的 hypothesis.updated 事件
    rounds: list[InvestigationRound]
    total_claims: int
    gap_resolved: bool  # 信息缺口是否缩小
    final_posteriors: dict[str, float]

class InvestigationAgent:
    def __init__(self, db_session, llm, searxng, gdelt_client, qdrant):
        ...

    async def investigate(self, case_uid: str, trigger_event: AegiEvent) -> InvestigationResult:
        """执行自主调研循环。"""
        # 1. 获取当前贝叶斯状态和证据缺口
        # 2. 用 LLM 把缺口描述转为搜索 query（多个角度）
        # 3. 执行搜索（SearXNG + GDELT）
        # 4. 搜索结果进入 ingest pipeline（提取 claim）
        # 5. claim.extracted 会自动触发贝叶斯更新
        # 6. 检查：缺口是否缩小？
        #    - 是：记录结果，通知专家
        #    - 否且未达 max_rounds：调整搜索策略，回到 2
        #    - 否且已达 max_rounds：记录结果，通知专家"需要人工介入"
        ...

    async def _generate_search_queries(self, gaps: list[dict], case_context: str) -> list[str]:
        """用 LLM 把证据缺口转为具体搜索 query。"""
        ...

    async def _execute_searches(self, queries: list[str]) -> list[dict]:
        """执行多源搜索，返回结果列表。"""
        ...

    async def _ingest_results(self, results: list[dict], case_uid: str) -> list[str]:
        """把搜索结果写入 AEGI pipeline，返回 claim_uids。"""
        ...
```

### 任务 2：注册 investigation_handler 到 EventBus

在 `src/aegi_core/api/main.py` 的启动逻辑中，新增：

```python
from aegi_core.services.investigation_agent import create_investigation_handler

# 在现有 handler 注册之后
investigation_handler = create_investigation_handler(llm=llm_client, searxng=searxng, gdelt=gdelt_client)
event_bus.subscribe("hypothesis.updated", investigation_handler)
```

`create_investigation_handler` 工厂函数的模式参考现有的 `create_push_handler` 和 `create_bayesian_update_handler`。

### 任务 3：调研记录持久化

新增 DB 模型 `src/aegi_core/db/models/investigation.py`：

```python
class Investigation(Base):
    __tablename__ = "investigations"

    uid: str                    # PK
    case_uid: str               # FK -> cases
    trigger_event_type: str     # 触发事件类型
    trigger_event_uid: str      # 触发事件 UID
    status: str                 # "running" | "completed" | "failed" | "cancelled"
    config: dict                # 使用的配置快照
    rounds: list[dict]          # JSON array of InvestigationRound
    total_claims_extracted: int
    gap_resolved: bool
    started_at: datetime
    completed_at: datetime | None
    cancelled_by: str | None    # 如果被专家取消
    created_at: datetime
```

- Alembic migration
- 新增 API：
  - `GET /api/investigations?case_uid=xxx` — 查看调研历史
  - `POST /api/investigations/{uid}/cancel` — 专家取消正在进行的调研
  - `GET /api/investigations/{uid}` — 查看单次调研详情

### 任务 4：settings 配置项

在 `settings.py` 中新增：

```python
# Investigation Agent
investigation_enabled: bool = True
investigation_max_rounds: int = 3
investigation_min_posterior_diff: float = 0.15
investigation_min_change_threshold: float = 0.05
investigation_cooldown_seconds: int = 300
investigation_max_concurrent: int = 3
investigation_token_budget_per_round: int = 10000
investigation_search_sources: str = "searxng,gdelt"  # 逗号分隔
```

### 任务 5：修复 crawler 配置冲突

检查 `deploy/openclaw.yaml`，确认 crawler agent 是否被禁止调用 `aegi_submit_evidence`。

两个方案选一个：
- 方案 A：放开 crawler 的 `aegi_submit_evidence` 权限
- 方案 B：InvestigationAgent 不走 `dispatch_research`（不依赖 OpenClaw agent），而是直接在 Python 层调用 SearXNG + ingest pipeline

**推荐方案 B**：InvestigationAgent 直接调用 `searxng_client.search()` + `ingest_helpers` 写入证据，不绕 OpenClaw agent。这样更简单、更可控、延迟更低。`dispatch_research` 保留给需要 agent 深度调研的场景。

## 安全边界

- `investigation_max_rounds` 限制搜索深度
- `investigation_cooldown_seconds` 防止同一 case 频繁触发
- `investigation_max_concurrent` 限制并发
- `investigation_token_budget_per_round` 控制 LLM 成本
- 专家可随时通过 API 取消调研
- 调研结果通过 `notify_user` 推送给专家，不自动做决策

## 验证

```bash
source .venv/bin/activate && source env.sh
python -m pytest tests/ -x --tb=short -q \
  --ignore=tests/test_feedback_service.py \
  --ignore=tests/test_stub_routes_integration.py
```

重点测试：
- `tests/test_investigation_agent.py` — 单元测试（mock LLM + SearXNG）
- 验证完整事件链：`hypothesis.updated` → investigation_handler → search → ingest → `claim.extracted` → bayesian_update
