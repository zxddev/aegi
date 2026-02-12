# Phase 1-C：Assertion 反馈 API + DB 模型（给 Claude Code）

## 任务

新增 Assertion 反馈机制，让分析师可以对 Assertion 给出反馈（同意/不同意/需要更多证据），为后续的自适应推送和信任校准打基础。

**在开始前，先阅读：**
- `src/aegi_core/db/models/assertion.py` — Assertion DB 模型
- `src/aegi_core/db/models/` — 其他模型的写法（学习约定）
- `src/aegi_core/api/routes/assertions.py` — 现有 Assertion API
- `src/aegi_core/contracts/schemas.py` — AssertionV1 等 schema
- `src/aegi_core/services/event_bus.py` — EventBus（反馈需要 emit 事件）
- `src/aegi_core/services/push_engine.py` — PushEngine（后续消费反馈数据）
- `docs/design/optimization-roadmap.md` — Phase 1.3 部分

## 实现步骤

### Step 1：新建 DB 模型

新建 `src/aegi_core/db/models/assertion_feedback.py`：

```python
"""分析师对 Assertion 的反馈记录。"""

from __future__ import annotations
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class AssertionFeedback(Base):
    __tablename__ = "assertion_feedback"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    assertion_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("assertions.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)

    # 反馈类型
    verdict: Mapped[str] = mapped_column(
        sa.String(32), nullable=False
    )  # agree | disagree | need_more_evidence | partially_agree

    # 可选：分析师手动校准的置信度
    confidence_override: Mapped[float | None] = mapped_column(sa.Float())

    # 可选：文字说明
    comment: Mapped[str | None] = mapped_column(sa.Text())

    # 可选：分析师认为的正确值（当 disagree 时）
    suggested_value: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        # 同一用户对同一 assertion 只能有一条有效反馈（最新的覆盖）
        sa.Index("ix_feedback_user_assertion", "user_id", "assertion_uid"),
    )
```

### Step 2：Alembic Migration

```bash
cd /home/user/workspace/gitcode/aegi/code/aegi-core
source .venv/bin/activate
alembic revision --autogenerate -m "add assertion_feedback table"
alembic upgrade head
```

确保 migration 文件正确生成。如果 autogenerate 没检测到新模型，检查 `db/models/__init__.py` 是否导入了 `AssertionFeedback`。

### Step 3：Pydantic Schema

在 `src/aegi_core/contracts/schemas.py` 中新增：

```python
class AssertionFeedbackCreate(BaseModel):
    """创建反馈的请求体。"""
    user_id: str
    verdict: Literal["agree", "disagree", "need_more_evidence", "partially_agree"]
    confidence_override: float | None = Field(None, ge=0.0, le=1.0)
    comment: str | None = Field(None, max_length=2000)
    suggested_value: dict | None = None

class AssertionFeedbackV1(BaseModel):
    """反馈响应体。"""
    uid: str
    assertion_uid: str
    case_uid: str
    user_id: str
    verdict: str
    confidence_override: float | None = None
    comment: str | None = None
    suggested_value: dict | None = None
    created_at: datetime

class AssertionFeedbackSummary(BaseModel):
    """某个 Assertion 的反馈汇总。"""
    assertion_uid: str
    total_feedback: int
    agree_count: int
    disagree_count: int
    need_more_evidence_count: int
    partially_agree_count: int
    avg_confidence_override: float | None = None  # 有 override 的平均值
    consensus: str  # "agreed" | "disputed" | "uncertain" | "no_feedback"
```

### Step 4：Service 层

新建 `src/aegi_core/services/feedback_service.py`：

```python
"""Assertion 反馈服务。"""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.models.assertion_feedback import AssertionFeedback
from aegi_core.db.models.assertion import Assertion
from aegi_core.services.event_bus import AegiEvent, get_event_bus


async def create_feedback(
    db: AsyncSession,
    *,
    assertion_uid: str,
    user_id: str,
    verdict: str,
    confidence_override: float | None = None,
    comment: str | None = None,
    suggested_value: dict | None = None,
) -> AssertionFeedback:
    """创建或更新反馈。

    同一用户对同一 assertion 的反馈会覆盖（upsert 语义）。

    流程：
    1. 验证 assertion 存在
    2. 查找该用户对该 assertion 的已有反馈
    3. 如果存在，更新；否则创建
    4. emit "assertion.feedback_received" 事件到 EventBus
    """


async def get_feedback_summary(
    db: AsyncSession,
    assertion_uid: str,
) -> dict:
    """获取某个 Assertion 的反馈汇总。

    返回：
    {
        "assertion_uid": "...",
        "total_feedback": 3,
        "agree_count": 2,
        "disagree_count": 1,
        "need_more_evidence_count": 0,
        "partially_agree_count": 0,
        "avg_confidence_override": 0.85,
        "consensus": "agreed",  # 多数同意
    }

    consensus 判定规则：
    - agree_count > total/2 → "agreed"
    - disagree_count > total/2 → "disputed"
    - need_more_evidence_count > total/2 → "uncertain"
    - 否则 → "mixed"
    - total == 0 → "no_feedback"
    """


async def get_user_feedback_history(
    db: AsyncSession,
    user_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[AssertionFeedback]:
    """获取某用户的反馈历史。"""


async def get_case_feedback_stats(
    db: AsyncSession,
    case_uid: str,
) -> dict:
    """获取某个 Case 下所有 Assertion 的反馈统计。

    返回：
    {
        "case_uid": "...",
        "total_assertions": 10,
        "assertions_with_feedback": 6,
        "feedback_coverage": 0.6,
        "overall_agreement_rate": 0.75,
        "disputed_assertions": ["uid1", "uid2"],
    }
    """
```

### Step 5：API 端点

在 `src/aegi_core/api/routes/assertions.py` 中新增端点：

```python
# POST /assertions/{assertion_uid}/feedback
# 创建或更新反馈
# Request: AssertionFeedbackCreate
# Response: AssertionFeedbackV1 (200)

# GET /assertions/{assertion_uid}/feedback
# 获取某 Assertion 的所有反馈
# Response: list[AssertionFeedbackV1]

# GET /assertions/{assertion_uid}/feedback/summary
# 获取反馈汇总
# Response: AssertionFeedbackSummary

# GET /cases/{case_uid}/feedback/stats
# 获取 Case 级别的反馈统计
# Response: CaseFeedbackStats（在 cases.py 或 assertions.py 中）

# DELETE /assertions/{assertion_uid}/feedback/{feedback_uid}
# 删除反馈（仅限反馈创建者）
```

### Step 6：EventBus 集成

反馈创建时 emit 事件：

```python
await event_bus.emit(AegiEvent(
    event_type="assertion.feedback_received",
    severity="low",
    payload={
        "assertion_uid": assertion_uid,
        "case_uid": case_uid,
        "user_id": user_id,
        "verdict": verdict,
        "confidence_override": confidence_override,
    },
))
```

这个事件后续会被 PushEngine 消费（Phase 6），用于调整推送阈值。当前只需要 emit，不需要 handler。

### Step 7：测试

`tests/test_feedback_service.py`：

```python
# 基础 CRUD
async def test_create_feedback():
    """创建反馈成功"""

async def test_create_feedback_assertion_not_found():
    """assertion 不存在时返回 404"""

async def test_upsert_feedback():
    """同一用户对同一 assertion 的反馈会覆盖"""

async def test_delete_feedback():
    """删除反馈成功"""

# 汇总
async def test_feedback_summary_agreed():
    """多数 agree → consensus='agreed'"""

async def test_feedback_summary_disputed():
    """多数 disagree → consensus='disputed'"""

async def test_feedback_summary_no_feedback():
    """无反馈 → consensus='no_feedback'"""

async def test_feedback_summary_mixed():
    """意见分散 → consensus='mixed'"""

async def test_avg_confidence_override():
    """有 override 时计算平均值"""

# Case 级别统计
async def test_case_feedback_stats():
    """Case 级别统计正确"""

async def test_case_feedback_coverage():
    """feedback_coverage 计算正确"""

# EventBus
async def test_feedback_emits_event():
    """创建反馈时 emit assertion.feedback_received"""

# API 端点
async def test_api_create_feedback():
    """POST /assertions/{uid}/feedback 返回 200"""

async def test_api_get_feedback_summary():
    """GET /assertions/{uid}/feedback/summary 返回正确汇总"""

async def test_api_validation():
    """无效 verdict 返回 422"""

async def test_api_confidence_override_range():
    """confidence_override 超出 0-1 范围返回 422"""
```

## 关键约束

- **不修改 Assertion 模型**：反馈是独立表，通过 FK 关联
- **Upsert 语义**：同一用户对同一 assertion 只保留最新反馈
- **verdict 枚举严格**：只允许 agree/disagree/need_more_evidence/partially_agree
- **confidence_override 范围**：0.0-1.0，Pydantic 验证
- **EventBus 只 emit 不 handle**：handler 在后续 Phase 实现
- **现有测试不能 break**
- **全量 pytest 0 failed**
