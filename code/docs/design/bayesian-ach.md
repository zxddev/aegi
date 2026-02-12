# AEGI 贝叶斯 ACH 详细设计

> 基于 bayesian-ach-guide.md 架构指导
> 日期：2026-02-11
> 状态：待实现

---

## 一、数据模型

### 1.1 hypotheses 表新增字段

在现有 `Hypothesis` 模型（`db/models/hypothesis.py`）上新增 3 个字段：

```python
# db/models/hypothesis.py 新增字段
prior_probability: Mapped[float | None] = mapped_column(
    sa.Float(), default=None, comment="先验概率（初始 = 1/N）"
)
posterior_probability: Mapped[float | None] = mapped_column(
    sa.Float(), default=None, comment="当前后验概率"
)
probability_history: Mapped[list[dict]] = mapped_column(
    JSONB, default=list, nullable=False,
    comment="概率变化轨迹 [{evidence_uid, prior, posterior, likelihood, timestamp}]"
)
```

字段语义：
- `prior_probability`：创建时设为 `1/N`（N = 同 case 下假设总数），专家可手动覆盖
- `posterior_probability`：每次贝叶斯更新后写入最新后验，初始 = prior
- `probability_history`：JSONB 数组，每条记录一次贝叶斯更新的完整快照

`probability_history` 单条结构：

```json
{
  "evidence_uid": "sc_abc123",
  "prior": 0.333,
  "posterior": 0.451,
  "likelihood": 0.85,
  "likelihood_ratio": 2.43,
  "timestamp": "2026-02-11T10:30:00Z"
}
```

### 1.2 新增 evidence_assessments 表

完整 SQLAlchemy 模型：

```python
# db/models/evidence_assessment.py

from __future__ import annotations
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class EvidenceAssessment(Base):
    __tablename__ = "evidence_assessments"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    hypothesis_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("hypotheses.uid", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    evidence_uid: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, index=True,
        comment="指向 assertion.uid 或 source_claim.uid"
    )
    evidence_type: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="assertion",
        comment="assertion | source_claim"
    )
    relation: Mapped[str] = mapped_column(
        sa.String(16), nullable=False,
        comment="support | contradict | irrelevant"
    )
    strength: Mapped[float] = mapped_column(
        sa.Float(), nullable=False,
        comment="LLM 给出的强度 0.0~1.0"
    )
    likelihood: Mapped[float] = mapped_column(
        sa.Float(), nullable=False,
        comment="转换后的 P(E|H)"
    )
    assessed_by: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="llm",
        comment="llm | expert"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        sa.Index("ix_ea_hyp_evidence", "hypothesis_uid", "evidence_uid"),
        sa.UniqueConstraint(
            "hypothesis_uid", "evidence_uid", name="uq_ea_hyp_evidence"
        ),
    )
```

唯一约束 `(hypothesis_uid, evidence_uid)` 确保同一条证据对同一假设只有一条评估记录。专家覆盖时 upsert。

---

## 二、Alembic Migration

Revision ID: `d4e5f6a7b8c9`，依赖 `c3d4e5f6a7b8`（event-driven tables）。

```python
"""Add Bayesian ACH: hypotheses new columns + evidence_assessments table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # hypotheses 表新增字段
    op.add_column("hypotheses", sa.Column(
        "prior_probability", sa.Float(), nullable=True,
    ))
    op.add_column("hypotheses", sa.Column(
        "posterior_probability", sa.Float(), nullable=True,
    ))
    op.add_column("hypotheses", sa.Column(
        "probability_history", JSONB, nullable=False, server_default="[]",
    ))

    # evidence_assessments 新表
    op.create_table(
        "evidence_assessments",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column("case_uid", sa.String(64),
                  sa.ForeignKey("cases.uid", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("hypothesis_uid", sa.String(64),
                  sa.ForeignKey("hypotheses.uid", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("evidence_uid", sa.String(64), nullable=False, index=True),
        sa.Column("evidence_type", sa.String(16), nullable=False,
                  server_default="assertion"),
        sa.Column("relation", sa.String(16), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("likelihood", sa.Float(), nullable=False),
        sa.Column("assessed_by", sa.String(16), nullable=False,
                  server_default="llm"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_ea_hyp_evidence", "evidence_assessments",
                    ["hypothesis_uid", "evidence_uid"])
    op.create_unique_constraint("uq_ea_hyp_evidence", "evidence_assessments",
                                ["hypothesis_uid", "evidence_uid"])


def downgrade() -> None:
    op.drop_table("evidence_assessments")
    op.drop_column("hypotheses", "probability_history")
    op.drop_column("hypotheses", "posterior_probability")
    op.drop_column("hypotheses", "prior_probability")
```

---

## 三、似然度映射表

LLM 输出 `(relation, strength)` → 转换为 `P(E|H)`。

### 3.1 连续映射函数

```python
def relation_strength_to_likelihood(relation: str, strength: float) -> float:
    """将 (relation, strength) 映射为 P(E|H)。

    - support:    线性插值 [0.55, 0.95]，strength 0→1
    - contradict: 线性插值 [0.45, 0.05]，strength 0→1
    - irrelevant: 固定 0.50
    """
    strength = max(0.0, min(1.0, strength))

    if relation == "support":
        return 0.55 + 0.40 * strength       # 0.55 ~ 0.95
    elif relation == "contradict":
        return 0.45 - 0.40 * strength       # 0.45 ~ 0.05
    else:  # irrelevant
        return 0.50
```

### 3.2 映射值域

| relation    | strength | P(E\|H) | 含义                                    |
|-------------|----------|---------|----------------------------------------|
| support     | 1.0      | 0.95    | 强支持：如果 H 为真，几乎必然看到 E         |
| support     | 0.7      | 0.83    | 中强支持                                 |
| support     | 0.5      | 0.75    | 中等支持                                 |
| support     | 0.0      | 0.55    | 弱支持：略高于随机                         |
| irrelevant  | any      | 0.50    | 无信息：不影响概率                         |
| contradict  | 0.0      | 0.45    | 弱反驳：略低于随机                         |
| contradict  | 0.5      | 0.25    | 中等反驳                                 |
| contradict  | 0.7      | 0.17    | 中强反驳                                 |
| contradict  | 1.0      | 0.05    | 强反驳：如果 H 为真，几乎不可能看到 E       |

设计要点：
- P(E|H) 永远不取 0 或 1，避免概率坍缩（一条证据就把假设杀死）
- support 和 contradict 关于 0.5 对称
- 可通过 Settings 配置覆盖默认区间

### 3.3 新增 Settings 字段

```python
# settings.py 新增
bayesian_likelihood_support_range: str = "0.55,0.95"   # min,max
bayesian_likelihood_contradict_range: str = "0.05,0.45" # min,max
bayesian_update_threshold: float = 0.05  # 概率变化 > 5% 才 emit 事件
```

---

## 四、BayesianACH 类接口设计

文件：`services/bayesian_ach.py`

### 4.1 LLM 评估 Pydantic 模型

```python
class EvidenceJudgment(BaseModel):
    """LLM 对单条证据与单个假设关系的判断。"""
    hypothesis_uid: str
    relation: Literal["support", "contradict", "irrelevant"]
    strength: float = Field(ge=0.0, le=1.0, description="判断强度")
    reason: str = ""


class EvidenceAssessmentRequest(BaseModel):
    """LLM 批量评估请求的 structured output。"""
    judgments: list[EvidenceJudgment]
```

### 4.2 返回值数据类

```python
@dataclass
class BayesianUpdateResult:
    """单次贝叶斯更新的完整结果。"""
    evidence_uid: str
    prior_distribution: dict[str, float]      # {hypothesis_uid: prior}
    posterior_distribution: dict[str, float]   # {hypothesis_uid: posterior}
    likelihoods: dict[str, float]             # {hypothesis_uid: P(E|H)}
    diagnosticity: dict[str, float]           # {hypothesis_uid: max LR vs others}
    max_change: float                         # 最大概率变化绝对值
    most_affected_hypothesis_uid: str         # 变化最大的假设


@dataclass
class BayesianState:
    """当前贝叶斯 ACH 完整状态。"""
    case_uid: str
    hypotheses: list[dict]  # [{uid, label, prior, posterior, history}]
    total_evidence_count: int
    last_updated: datetime | None
```

### 4.3 BayesianACH 类

```python
class BayesianACH:
    """贝叶斯竞争性假设分析引擎。

    不引入任何贝叶斯网络库，直接实现贝叶斯公式。
    LLM 负责定性判断（relation + strength），数学负责定量计算。
    """

    def __init__(
        self,
        db_session: AsyncSession,
        llm: LLMClient,
    ) -> None: ...

    # ── 初始化 ──

    async def initialize_priors(
        self,
        case_uid: str,
        hypothesis_uids: list[str] | None = None,
    ) -> dict[str, float]:
        """为 case 下所有假设设置均匀先验。

        如果 hypothesis_uids 指定，只初始化这些假设。
        已有 prior 的假设不会被覆盖（除非 force=True）。

        Returns: {hypothesis_uid: prior_probability}
        """

    # ── 证据评估 ──

    async def assess_evidence(
        self,
        case_uid: str,
        evidence_uid: str,
        evidence_text: str,
        evidence_type: str = "assertion",
    ) -> list[EvidenceAssessment]:
        """用 LLM 评估一条证据与所有假设的关系。

        流程：
        1. 加载 case 下所有假设
        2. 构建 prompt，让 LLM 判断 evidence 与每个假设的 relation + strength
        3. 将 (relation, strength) 映射为 likelihood P(E|H)
        4. 持久化到 evidence_assessments 表
        5. 返回评估结果列表

        Returns: 每个假设一条 EvidenceAssessment DB 行
        """

    # ── 贝叶斯更新 ──

    async def update(
        self,
        case_uid: str,
        evidence_uid: str,
    ) -> BayesianUpdateResult:
        """基于已有的 evidence_assessments 执行贝叶斯更新。

        核心公式：
          P(H_i | E) = P(E | H_i) * P(H_i) / P(E)
          P(E) = Σ P(E | H_j) * P(H_j)

        流程：
        1. 加载 case 下所有假设的当前 posterior（作为本次 prior）
        2. 加载该 evidence_uid 对所有假设的 likelihood
        3. 计算 P(E) = Σ P(E|H_j) * P(H_j)
        4. 对每个假设计算新 posterior
        5. 归一化确保 Σ posterior = 1.0
        6. 更新 hypotheses 表的 posterior_probability
        7. 追加 probability_history 记录
        8. 返回 BayesianUpdateResult

        Returns: 更新结果，包含前后概率分布和诊断性
        """

    # ── 查询 ──

    async def get_state(self, case_uid: str) -> BayesianState:
        """返回 case 下所有假设的当前概率分布 + 历史轨迹。"""

    async def get_diagnosticity_ranking(
        self,
        case_uid: str,
    ) -> list[dict]:
        """返回所有已评估证据的诊断性排名。

        诊断性 = max(P(E|H_i) / P(E|H_j)) for all i≠j
        诊断性越高，该证据对区分假设越有价值。

        Returns: [{evidence_uid, diagnosticity, most_discriminated_pair: (H_i, H_j)}]
        """

    async def get_evidence_gaps(
        self,
        case_uid: str,
    ) -> list[dict]:
        """识别最有价值的信息缺口。

        找出哪些假设之间的后验概率接近（难以区分），
        然后建议需要什么类型的证据来区分它们。

        Returns: [{hypothesis_pair, posterior_diff, suggested_evidence_type}]
        """

    # ── 专家覆盖 ──

    async def override_assessment(
        self,
        assessment_uid: str,
        relation: str,
        strength: float,
    ) -> EvidenceAssessment:
        """专家手动覆盖 LLM 的评估。

        更新 evidence_assessments 行的 relation/strength/likelihood，
        标记 assessed_by="expert"。
        调用方需要随后调用 recalculate() 重新计算后验。
        """

    async def recalculate(self, case_uid: str) -> dict[str, float]:
        """从头重新计算所有后验概率（用于专家覆盖后）。

        按 evidence_assessments.created_at 顺序，
        从均匀先验开始，依次应用每条证据的贝叶斯更新。

        Returns: {hypothesis_uid: posterior_probability}
        """
```

### 4.4 LLM Prompt 设计

评估单条证据对所有假设的关系：

```python
_ASSESS_PROMPT = """\
你是一名情报分析师。给定一条新证据和多个竞争性假设，
判断该证据与每个假设的关系。

证据：{evidence_text}

假设列表：
{hypotheses_text}

对每个假设，判断：
- relation: "support"（支持）/ "contradict"（反驳）/ "irrelevant"（无关）
- strength: 0.0~1.0 的强度值
  - 1.0 = 非常强的支持/反驳
  - 0.5 = 中等
  - 0.0 = 非常弱
- reason: 简短理由

注意：
- 不要输出概率数值，只判断关系和强度
- 同一条证据可以同时支持某些假设、反驳另一些假设
- 如果证据与假设无关，strength 值无意义，设为 0.5 即可
"""
```

---

## 五、事件驱动集成

### 5.1 完整流程

```
claim.extracted 事件
    │
    ▼
EventBus handler: bayesian_update_handler
    │
    ├─ 1. 从 event.payload 提取 claim_uids
    ├─ 2. 加载 case 下所有假设（如果没有假设，跳过）
    ├─ 3. 对每条新 claim：
    │     ├─ 加载 claim 文本
    │     ├─ BayesianACH.assess_evidence() → LLM 评估
    │     └─ BayesianACH.update() → 贝叶斯更新
    ├─ 4. 检查 max_change > bayesian_update_threshold (默认 5%)
    └─ 5. 如果超过阈值：
          └─ emit AegiEvent(
                event_type="hypothesis.updated",
                case_uid=case_uid,
                severity="medium",
                payload={
                    "summary": "假设概率更新：H_A 60%→75% (+15%)",
                    "updates": [
                        {"hypothesis_uid": "...", "label": "...",
                         "prior": 0.60, "posterior": 0.75, "change": 0.15},
                        ...
                    ],
                    "trigger_evidence_uid": "...",
                    "trigger_evidence_text": "...",
                    "diagnosticity": 4.5,
                },
            )
              │
              ▼
          PushEngine 处理 hypothesis.updated
              → 匹配订阅了该 case 的专家
              → 推送概率变化通知
```

### 5.2 Handler 注册

```python
# services/bayesian_ach.py 底部

def create_bayesian_update_handler(
    *,
    llm: LLMClient | None = None,
) -> EventHandler:
    """创建 claim.extracted 事件的 handler。"""

    async def bayesian_update_handler(event: AegiEvent) -> None:
        if event.event_type != "claim.extracted":
            return

        case_uid = event.case_uid
        claim_uids = event.payload.get("claim_uids", [])
        if not claim_uids:
            return

        from aegi_core.db.session import ENGINE
        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            # 检查 case 下是否有假设
            hyp_count = (await session.execute(
                sa.select(sa.func.count()).select_from(Hypothesis)
                .where(Hypothesis.case_uid == case_uid)
            )).scalar_one()
            if hyp_count == 0:
                return

            if llm is None:
                return

            engine = BayesianACH(session, llm)

            for claim_uid in claim_uids:
                # 加载 claim 文本
                claim = await session.get(SourceClaim, claim_uid)
                if not claim:
                    continue

                # 评估 + 更新
                await engine.assess_evidence(
                    case_uid=case_uid,
                    evidence_uid=claim_uid,
                    evidence_text=claim.quote,
                    evidence_type="source_claim",
                )
                result = await engine.update(case_uid, claim_uid)

                # 超过阈值则 emit hypothesis.updated
                from aegi_core.settings import settings
                if result.max_change >= settings.bayesian_update_threshold:
                    updates = [
                        {
                            "hypothesis_uid": uid,
                            "prior": result.prior_distribution[uid],
                            "posterior": result.posterior_distribution[uid],
                            "change": result.posterior_distribution[uid]
                                     - result.prior_distribution[uid],
                        }
                        for uid in result.posterior_distribution
                    ]
                    bus = get_event_bus()
                    await bus.emit(AegiEvent(
                        event_type="hypothesis.updated",
                        case_uid=case_uid,
                        payload={
                            "summary": _format_update_summary(updates),
                            "updates": updates,
                            "trigger_evidence_uid": claim_uid,
                            "trigger_evidence_text": claim.quote[:200],
                            "max_change": result.max_change,
                        },
                        severity="medium",
                        source_event_uid=f"bayes:{case_uid}:{claim_uid}",
                    ))

            await session.commit()

    bayesian_update_handler.__name__ = "bayesian_update_handler"
    return bayesian_update_handler
```

### 5.3 应用启动时注册

```python
# api/main.py lifespan 中
from aegi_core.services.bayesian_ach import create_bayesian_update_handler

bus = get_event_bus()
bus.on("claim.extracted", create_bayesian_update_handler(llm=llm_client))
```

### 5.4 推送消息格式

`hypothesis.updated` 事件被 PushEngine 处理后，专家收到的通知：

```
[案例: {case_uid}] 假设概率更新

  假设A "伊朗将在3个月内重启核谈判"
    60.0% → 75.3% (+15.3%)
  假设B "伊朗将加速铀浓缩"
    25.0% → 15.2% (-9.8%)
  假设C "维持现状"
    15.0% → 9.5% (-5.5%)

触发证据：[Reuters] "伊朗外长表示愿意在特定条件下恢复对话"
诊断性：该证据强烈区分假设A和假设B（诊断比=4.5）
```

---

## 六、API 端点设计

### 6.1 GET /cases/{case_uid}/hypotheses/probabilities

返回当前概率分布和历史轨迹。

```
GET /cases/{case_uid}/hypotheses/probabilities

Response 200:
{
  "case_uid": "case_001",
  "hypotheses": [
    {
      "hypothesis_uid": "hyp_abc",
      "label": "伊朗将在3个月内重启核谈判",
      "prior_probability": 0.333,
      "posterior_probability": 0.753,
      "history": [
        {
          "evidence_uid": "sc_001",
          "prior": 0.333,
          "posterior": 0.451,
          "likelihood": 0.85,
          "likelihood_ratio": 2.43,
          "timestamp": "2026-02-11T10:30:00Z"
        },
        ...
      ]
    },
    ...
  ],
  "total_evidence_assessed": 12,
  "last_updated": "2026-02-11T14:22:00Z"
}
```

### 6.2 POST /cases/{case_uid}/hypotheses/bayesian-update

手动触发贝叶斯更新（不等 claim.extracted 事件）。

```
POST /cases/{case_uid}/hypotheses/bayesian-update

Request:
{
  "evidence_uid": "sc_abc123",
  "evidence_text": "伊朗外长表示...",
  "evidence_type": "source_claim"
}

Response 200:
{
  "evidence_uid": "sc_abc123",
  "prior_distribution": {"hyp_a": 0.60, "hyp_b": 0.25, "hyp_c": 0.15},
  "posterior_distribution": {"hyp_a": 0.753, "hyp_b": 0.152, "hyp_c": 0.095},
  "likelihoods": {"hyp_a": 0.85, "hyp_b": 0.20, "hyp_c": 0.50},
  "diagnosticity": {"hyp_a": 4.25, "hyp_b": 0.24, "hyp_c": 1.0},
  "max_change": 0.153,
  "most_affected_hypothesis_uid": "hyp_a"
}
```

### 6.3 POST /cases/{case_uid}/hypotheses/initialize-priors

初始化或重置先验概率。

```
POST /cases/{case_uid}/hypotheses/initialize-priors

Request (可选):
{
  "priors": {"hyp_a": 0.5, "hyp_b": 0.3, "hyp_c": 0.2}
}

Response 200:
{
  "priors": {"hyp_a": 0.5, "hyp_b": 0.3, "hyp_c": 0.2}
}
```

如果不传 `priors`，使用均匀分布 `1/N`。传入的 priors 必须归一化（和为 1.0）。

### 6.4 PUT /cases/{case_uid}/evidence-assessments/{assessment_uid}

专家覆盖 LLM 评估。

```
PUT /cases/{case_uid}/evidence-assessments/{assessment_uid}

Request:
{
  "relation": "support",
  "strength": 0.9
}

Response 200:
{
  "uid": "ea_xxx",
  "hypothesis_uid": "hyp_a",
  "evidence_uid": "sc_001",
  "relation": "support",
  "strength": 0.9,
  "likelihood": 0.91,
  "assessed_by": "expert"
}
```

覆盖后需调用 `recalculate` 重新计算后验。可在响应中自动触发，或由前端调用 6.5。

### 6.5 POST /cases/{case_uid}/hypotheses/recalculate

专家覆盖评估后，从头重新计算所有后验。

```
POST /cases/{case_uid}/hypotheses/recalculate

Response 200:
{
  "posteriors": {"hyp_a": 0.72, "hyp_b": 0.18, "hyp_c": 0.10},
  "evidence_count": 15
}
```

### 6.6 GET /cases/{case_uid}/hypotheses/diagnosticity

返回证据诊断性排名。

```
GET /cases/{case_uid}/hypotheses/diagnosticity

Response 200:
{
  "rankings": [
    {
      "evidence_uid": "sc_005",
      "diagnosticity": 6.33,
      "most_discriminated": ["hyp_a", "hyp_b"]
    },
    {
      "evidence_uid": "sc_001",
      "diagnosticity": 4.25,
      "most_discriminated": ["hyp_a", "hyp_c"]
    },
    ...
  ]
}
```

### 6.7 路由注册

```python
# api/routes/bayesian.py
router = APIRouter(
    prefix="/cases/{case_uid}/hypotheses",
    tags=["bayesian-ach"],
)

# 在 api/main.py 中注册
from aegi_core.api.routes.bayesian import router as bayesian_router
app.include_router(bayesian_router)
```

---

## 七、测试计划

### 7.1 单元测试：贝叶斯数学正确性（test_bayesian_math.py）

| 测试用例 | 验证内容 |
|---------|---------|
| `test_uniform_prior` | N 个假设初始化后，每个 prior = 1/N，和 = 1.0 |
| `test_single_support_update` | 一条 support 证据后，被支持假设 posterior 上升，其他下降，和 = 1.0 |
| `test_single_contradict_update` | 一条 contradict 证据后，被反驳假设 posterior 下降 |
| `test_irrelevant_no_change` | irrelevant 证据不改变概率分布（P(E\|H)=0.5 对所有 H） |
| `test_strong_vs_weak_support` | strength=0.9 的 support 比 strength=0.3 的 support 导致更大概率变化 |
| `test_multiple_updates_normalize` | 连续 5 次更新后，所有后验之和仍 = 1.0（±1e-10） |
| `test_likelihood_mapping_symmetry` | support(s) 和 contradict(s) 关于 0.5 对称 |
| `test_likelihood_bounds` | P(E\|H) 始终在 (0, 1) 开区间内 |
| `test_diagnosticity_calculation` | 诊断性 = max(P(E\|H_i)/P(E\|H_j))，手动验证 |
| `test_recalculate_matches_sequential` | recalculate() 结果与逐条 update() 结果一致 |

### 7.2 单元测试：似然度映射（test_likelihood_mapping.py）

| 测试用例 | 验证内容 |
|---------|---------|
| `test_support_range` | support strength 0→1 映射到 0.55→0.95 |
| `test_contradict_range` | contradict strength 0→1 映射到 0.45→0.05 |
| `test_irrelevant_fixed` | irrelevant 任何 strength 都返回 0.50 |
| `test_clamp_out_of_range` | strength < 0 或 > 1 被 clamp |
| `test_custom_range_from_settings` | 自定义 Settings 区间生效 |

### 7.3 集成测试：LLM 评估（test_bayesian_assess.py）

| 测试用例 | 验证内容 |
|---------|---------|
| `test_assess_evidence_creates_records` | assess_evidence() 为每个假设创建一条 EvidenceAssessment |
| `test_assess_evidence_idempotent` | 同一 evidence_uid 重复评估不创建重复记录（upsert） |
| `test_assess_evidence_llm_failure_graceful` | LLM 失败时不崩溃，返回空列表 |

### 7.4 集成测试：事件驱动（test_bayesian_event_integration.py）

| 测试用例 | 验证内容 |
|---------|---------|
| `test_claim_extracted_triggers_update` | emit claim.extracted → handler 执行 → hypotheses 表 posterior 更新 |
| `test_no_hypotheses_skips` | case 下无假设时，handler 直接返回不报错 |
| `test_threshold_emits_hypothesis_updated` | 概率变化 > 5% 时 emit hypothesis.updated 事件 |
| `test_below_threshold_no_emit` | 概率变化 < 5% 时不 emit |
| `test_hypothesis_updated_reaches_push_engine` | hypothesis.updated 事件被 PushEngine 处理 |

### 7.5 API 测试（test_bayesian_api.py）

| 测试用例 | 验证内容 |
|---------|---------|
| `test_get_probabilities_empty` | 无假设时返回空列表 |
| `test_get_probabilities_after_update` | 更新后返回正确的 posterior 和 history |
| `test_initialize_priors_uniform` | 不传 priors 时均匀分布 |
| `test_initialize_priors_custom` | 传入自定义 priors，验证归一化检查 |
| `test_initialize_priors_invalid_sum` | priors 和 ≠ 1.0 时返回 422 |
| `test_manual_bayesian_update` | POST bayesian-update 返回正确的前后概率 |
| `test_expert_override` | PUT assessment → recalculate → 后验变化 |
| `test_diagnosticity_ranking` | 返回按诊断性降序排列的证据列表 |

### 7.6 测试策略

- 数学测试使用固定数值，不依赖 LLM（纯计算验证）
- LLM 评估测试使用 `llm.invoke_structured()` mock，返回固定 `EvidenceAssessmentRequest`
- 事件驱动测试使用 `emit_and_wait()` 确保 handler 执行完毕
- API 测试使用 `app.dependency_overrides` 注入 mock LLM 和 test DB session
- 所有测试不依赖外部服务（Neo4j、Qdrant、真实 LLM）

---

## 八、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `db/models/hypothesis.py` | 修改 | 新增 3 个字段 |
| `db/models/evidence_assessment.py` | 新建 | EvidenceAssessment 模型 |
| `db/models/__init__.py` | 修改 | 导出 EvidenceAssessment |
| `alembic/versions/d4e5f6a7b8c9_*.py` | 新建 | Migration |
| `services/bayesian_ach.py` | 新建 | BayesianACH 核心类 + handler |
| `api/routes/bayesian.py` | 新建 | 6 个 API 端点 |
| `api/main.py` | 修改 | 注册路由 + handler |
| `settings.py` | 修改 | 新增 3 个配置项 |
| `tests/test_bayesian_math.py` | 新建 | 10 个数学测试 |
| `tests/test_likelihood_mapping.py` | 新建 | 5 个映射测试 |
| `tests/test_bayesian_assess.py` | 新建 | 3 个 LLM 评估测试 |
| `tests/test_bayesian_event_integration.py` | 新建 | 5 个事件驱动测试 |
| `tests/test_bayesian_api.py` | 新建 | 8 个 API 测试 |

---

## 九、与现有代码的关系

```
现有流程（保留不变）：
  generate_hypotheses() → [ACHResult] → analyze_hypothesis_llm() → confidence
  evaluate_adversarial() / aevaluate_adversarial() → AdversarialResult

新增贝叶斯层（叠加在上面）：
  generate_hypotheses() → 存入 DB
      ↓
  BayesianACH.initialize_priors() → 设置均匀先验
      ↓
  新证据到来（claim.extracted 事件）
      ↓
  BayesianACH.assess_evidence() → LLM 判断 relation + strength
      ↓
  BayesianACH.update() → 贝叶斯公式计算后验
      ↓
  概率变化 > 阈值 → emit hypothesis.updated → PushEngine → 专家通知
```

BayesianACH 是现有 ACH 之上的增量层：
- 不修改 `ACHResult` 数据结构
- 不修改 `generate_hypotheses()` 和 `analyze_hypothesis_llm()` 的接口
- 不修改现有测试
- 现有的 confidence 字段（简单比例）保留，posterior_probability 是新的贝叶斯概率

---

_设计完成，待审核后进入实现。_