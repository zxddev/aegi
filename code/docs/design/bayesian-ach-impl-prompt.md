# 贝叶斯 ACH 实现提示词（给 Claude Code）

## 任务

基于 `docs/design/bayesian-ach.md` 详细设计文档，实现贝叶斯竞争性假设分析（Bayesian ACH）功能。

**在开始编码前，先完整阅读以下文件：**
- `docs/design/bayesian-ach-guide.md` — 架构指导
- `docs/design/bayesian-ach.md` — 详细设计（主文档）
- `src/aegi_core/db/models/hypothesis.py` — 现有 Hypothesis 模型
- `src/aegi_core/services/event.py` — EventBus 实现
- `src/aegi_core/services/push_engine.py` — PushEngine 实现
- `src/aegi_core/services/hypothesis_engine.py` — 现有 ACH 引擎
- `src/aegi_core/settings.py` — Settings 类
- `src/aegi_core/api/routes/hypotheses.py` — 现有假设路由
- `src/aegi_core/db/models/__init__.py` — 模型导出

## 架构审查修正（必须遵守）

详细设计文档整体通过审查，但有 **3 处必须修正**：

### 修正 1：probability_history 拆成独立表（🔴 必须改）

**问题：** 设计文档把 `probability_history` 放在 hypotheses 表的 JSONB 字段里。随着证据增多，这个 JSONB 数组会无限膨胀，每次更新要读出整个数组、append、写回，并发时有 race condition。

**修正方案：** 不在 hypotheses 表加 `probability_history` JSONB 字段。改为新建 `probability_updates` 表：

```python
class ProbabilityUpdate(Base):
    __tablename__ = "probability_updates"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    hypothesis_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("hypotheses.uid", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    evidence_uid: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    prior: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    posterior: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    likelihood: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    likelihood_ratio: Mapped[float | None] = mapped_column(sa.Float())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False,
    )
```

- hypotheses 表仍然加 `prior_probability` 和 `posterior_probability` 两个字段（这两个保留）
- 查询历史轨迹：`SELECT * FROM probability_updates WHERE hypothesis_uid = ? ORDER BY created_at`
- Alembic migration 相应调整：建 `probability_updates` 表，不加 `probability_history` JSONB 列
- `BayesianACH.update()` 方法中，每次更新插入一行 `ProbabilityUpdate`，而不是 append JSONB
- `BayesianACH.get_state()` 方法中，通过 JOIN 或子查询获取历史
- API 响应中的 `history` 字段从 `probability_updates` 表查询

### 修正 2：串行 LLM 调用加注释（🟡 保持串行，加注释）

**问题：** `bayesian_update_handler` 中 `for claim_uid in claim_uids` 是串行调用 LLM。

**修正方案：** 保持串行不变（因为后一条 claim 的 prior 依赖前一条的 posterior，并行会破坏贝叶斯更新的顺序性），但在代码中加明确注释：

```python
# 必须串行处理：每条 claim 的贝叶斯更新依赖前一条的 posterior 作为 prior。
# 不要改成 asyncio.gather 并行，否则概率计算会出错。
for claim_uid in claim_uids:
    ...
```

### 修正 3：get_evidence_gaps 用规则模板（🟡 不调 LLM）

**问题：** `get_evidence_gaps()` 的"建议什么证据"部分实现细节缺失。

**修正方案：** 用规则模板生成建议，不额外调 LLM：

```python
async def get_evidence_gaps(self, case_uid: str) -> list[dict]:
    """识别最有价值的信息缺口。"""
    # 1. 找出后验概率接近的假设对（差值 < 0.15）
    # 2. 对每对假设，生成规则化建议：
    #    - "需要能区分「{H_A}」和「{H_B}」的证据"
    #    - "寻找支持「{H_A}」但反驳「{H_B}」的信息，或反之"
    #    - 如果某假设缺少 contradict 类评估，提示"「{H_X}」尚未被任何证据反驳，建议寻找反面证据"
    # 3. 返回按 posterior_diff 升序排列（最难区分的排最前）
```

## 实现顺序

按以下顺序实现，每完成一步跑一次相关测试：

### Step 1：数据模型 + Migration
1. 修改 `db/models/hypothesis.py`：新增 `prior_probability`, `posterior_probability` 两个字段
2. 新建 `db/models/evidence_assessment.py`：按设计文档
3. 新建 `db/models/probability_update.py`：按修正 1
4. 修改 `db/models/__init__.py`：导出新模型
5. 新建 Alembic migration（注意 down_revision 要对上最新的 head）
6. 修改 `settings.py`：新增 3 个配置项

### Step 2：核心服务
1. 新建 `services/bayesian_ach.py`：
   - `relation_strength_to_likelihood()` 映射函数
   - `BayesianACH` 类的所有方法
   - `create_bayesian_update_handler()` 工厂函数
2. 注意 `update()` 方法写 `probability_updates` 表而不是 JSONB
3. 注意 handler 中串行处理 + 注释

### Step 3：API 路由
1. 新建 `api/routes/bayesian.py`：6 个端点
2. 修改 `api/main.py`：注册路由 + 在 lifespan 中注册 handler

### Step 4：测试
1. `tests/test_bayesian_math.py` — 10 个数学测试（最重要，先写）
2. `tests/test_likelihood_mapping.py` — 5 个映射测试
3. `tests/test_bayesian_assess.py` — 3 个 LLM 评估测试
4. `tests/test_bayesian_event_integration.py` — 5 个事件驱动测试
5. `tests/test_bayesian_api.py` — 8 个 API 测试

## 关键约束

- **不修改现有代码的行为**：BayesianACH 是增量叠加层，不动 `ACHResult`、`generate_hypotheses()`、`analyze_hypothesis_llm()` 的接口和逻辑
- **不引入新依赖**：不用 pgmpy 等贝叶斯库，贝叶斯公式自己写（几十行代码）
- **uid 生成**：遵循项目现有模式（检查其他模型怎么生成 uid 的，保持一致）
- **LLM 调用**：使用项目现有的 `LLMClient` + `instructor` structured output 模式
- **测试不依赖外部服务**：mock LLM，用 test DB session
- **现有测试不能 break**：实现完成后跑全量 `pytest`，确保 0 failed

## 验收标准

1. `pytest tests/test_bayesian_math.py tests/test_likelihood_mapping.py` 全绿
2. `pytest tests/test_bayesian_assess.py tests/test_bayesian_event_integration.py tests/test_bayesian_api.py` 全绿
3. `pytest` 全量测试 0 failed（包括之前的 299 个）
4. `alembic upgrade head` 成功
5. API 端点可通过 curl 手动验证
