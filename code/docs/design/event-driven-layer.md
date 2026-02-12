# AEGI 事件驱动层 — 详细设计

> 基于：event-driven-architecture-guide.md（白泽）
> 日期：2026-02-11

---

## 一、数据模型（SQLAlchemy 2 + Mapped）

### 1.1 subscriptions 表

```python
# db/models/subscription.py
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Subscription(Base):
    __tablename__ = "subscriptions"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.String(128), index=True, nullable=False)

    # case | entity | region | topic | global
    sub_type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    # 具体目标：case_uid / entity_uid / region_code / topic_tag / "*"
    sub_target: Mapped[str] = mapped_column(sa.String(256), nullable=False, default="*")

    # 只接收 >= 该优先级的事件（low=0, medium=1, high=2, critical=3）
    priority_threshold: Mapped[int] = mapped_column(sa.Integer(), default=0, nullable=False)

    # 事件类型过滤（空 = 全部）
    event_types: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()), default=list, nullable=False
    )

    enabled: Mapped[bool] = mapped_column(sa.Boolean(), default=True, nullable=False)

    # 专家兴趣描述（用于生成 embedding）
    interest_text: Mapped[str | None] = mapped_column(sa.Text())
    # 兴趣 embedding 是否已同步到 Qdrant
    embedding_synced: Mapped[bool] = mapped_column(sa.Boolean(), default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        sa.Index("ix_sub_type_target", "sub_type", "sub_target"),
    )
```

### 1.2 event_log 表

```python
# db/models/event_log.py
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class EventLog(Base):
    __tablename__ = "event_log"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(sa.String(64), index=True, nullable=False)
    case_uid: Mapped[str | None] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="SET NULL"),
        index=True,
    )

    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    entities: Mapped[list[str]] = mapped_column(ARRAY(sa.Text()), default=list, nullable=False)
    regions: Mapped[list[str]] = mapped_column(ARRAY(sa.Text()), default=list, nullable=False)
    topics: Mapped[list[str]] = mapped_column(ARRAY(sa.Text()), default=list, nullable=False)

    # low | medium | high | critical
    severity: Mapped[str] = mapped_column(sa.String(16), default="medium", nullable=False)
    # 去重标识（同一 source_event_uid 不重复处理）
    source_event_uid: Mapped[str] = mapped_column(sa.String(128), unique=True, nullable=False)

    # 处理状态：pending | processing | done | failed
    status: Mapped[str] = mapped_column(sa.String(16), default="pending", nullable=False)
    push_count: Mapped[int] = mapped_column(sa.Integer(), default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
```

### 1.3 push_log 表

```python
# db/models/push_log.py
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class PushLog(Base):
    __tablename__ = "push_log"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    event_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("event_log.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(sa.String(128), index=True, nullable=False)
    subscription_uid: Mapped[str | None] = mapped_column(sa.String(64))

    # rule | semantic | llm
    match_method: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    match_score: Mapped[float] = mapped_column(sa.Float(), default=1.0, nullable=False)
    match_reason: Mapped[str | None] = mapped_column(sa.Text())

    # delivered | throttled | failed
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(sa.Text())

    # 用户反馈：null=未反馈, true=有用, false=没用
    feedback: Mapped[bool | None] = mapped_column(sa.Boolean())

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
```

---

## 二、event_bus.py — 事件总线

### 2.1 事件数据类

```python
# services/event_bus.py
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class AegiEvent:
    """不可变事件对象，贯穿整个事件链路。"""

    event_type: str                          # "pipeline.completed"
    case_uid: str                            # 关联 case
    payload: dict[str, Any]                  # 事件详情
    entities: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    severity: str = "medium"                 # low / medium / high / critical
    source_event_uid: str = ""               # 去重标识（空则自动生成）
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.source_event_uid:
            object.__setattr__(self, "source_event_uid", uuid.uuid4().hex)
```

### 2.2 EventHandler 类型

```python
# 事件处理器签名
EventHandler = Callable[[AegiEvent], Awaitable[None]]
```

### 2.3 EventBus 类

```python
class EventBus:
    """进程内 asyncio 事件总线。

    - 支持按 event_type 注册 handler
    - 支持通配符 "*" 监听所有事件
    - emit 是 fire-and-forget（创建 asyncio.Task，不阻塞调用方）
    - 所有 handler 异常被捕获并记录，不影响其他 handler
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._running_tasks: set[asyncio.Task] = set()

    def on(self, event_type: str, handler: EventHandler) -> None:
        """注册事件处理器。event_type="*" 表示监听所有事件。"""
        self._handlers[event_type].append(handler)
        logger.info("EventBus: registered handler for %s: %s", event_type, handler.__name__)

    def off(self, event_type: str, handler: EventHandler) -> None:
        """移除事件处理器。"""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: AegiEvent) -> None:
        """发布事件。每个 handler 在独立 Task 中执行，不阻塞调用方。"""
        handlers = list(self._handlers.get(event.event_type, []))
        handlers.extend(self._handlers.get("*", []))

        if not handlers:
            logger.debug("EventBus: no handlers for %s", event.event_type)
            return

        for handler in handlers:
            task = asyncio.create_task(self._safe_call(handler, event))
            self._running_tasks.add(task)
            task.add_done_callback(self._running_tasks.discard)

    async def emit_and_wait(self, event: AegiEvent) -> None:
        """发布事件并等待所有 handler 完成（用于测试）。"""
        handlers = list(self._handlers.get(event.event_type, []))
        handlers.extend(self._handlers.get("*", []))
        await asyncio.gather(
            *(self._safe_call(h, event) for h in handlers),
            return_exceptions=True,
        )

    async def _safe_call(self, handler: EventHandler, event: AegiEvent) -> None:
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "EventBus: handler %s failed for event %s",
                handler.__name__, event.event_type,
            )

    async def drain(self) -> None:
        """等待所有正在执行的 handler 完成（用于 graceful shutdown）。"""
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
```

### 2.4 全局单例

```python
# 模块级单例，在 lifespan 中初始化
_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_event_bus() -> None:
    """测试用：重置全局 bus。"""
    global _bus
    _bus = None
```

---

## 三、push_engine.py — 推送决策引擎

### 3.1 匹配候选

```python
# services/push_engine.py
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.services.event_bus import AegiEvent, SEVERITY_RANK

logger = logging.getLogger(__name__)


@dataclass
class PushCandidate:
    """一次匹配结果。"""
    user_id: str
    subscription_uid: str | None
    match_method: str          # rule | semantic | llm
    match_score: float         # 0.0 ~ 1.0
    match_reason: str
```

### 3.2 PushEngine 类

```python
class PushEngine:
    """推送决策引擎。

    职责：
    1. 规则匹配 — 查 subscriptions 表
    2. 语义匹配 — 事件 embedding vs 专家 profile embedding（Qdrant）
    3. 合并去重
    4. 节流检查
    5. LLM 精排（可选）
    6. 投递 — 调用 dispatch.notify_user()
    """

    def __init__(
        self,
        db_session: AsyncSession,
        *,
        qdrant: Any | None = None,
        llm: Any | None = None,
        max_push_per_hour: int = 10,
        semantic_threshold: float = 0.65,
    ) -> None:
        self._db = db_session
        self._qdrant = qdrant
        self._llm = llm
        self._max_push_per_hour = max_push_per_hour
        self._semantic_threshold = semantic_threshold

    async def process_event(self, event: AegiEvent) -> int:
        """处理一个事件，返回实际推送数。

        完整流程：
        1. 持久化事件到 event_log
        2. 去重检查（source_event_uid）
        3. 规则匹配
        4. 语义匹配
        5. 合并去重
        6. 节流
        7. 投递 + 记录 push_log
        """
        from aegi_core.db.models.event_log import EventLog

        # 1. 去重：检查 source_event_uid 是否已存在
        existing = (await self._db.execute(
            sa.select(EventLog.uid).where(
                EventLog.source_event_uid == event.source_event_uid
            )
        )).scalar_one_or_none()
        if existing:
            logger.debug("Event %s already processed, skip", event.source_event_uid)
            return 0

        # 2. 持久化事件
        event_uid = uuid.uuid4().hex
        row = EventLog(
            uid=event_uid,
            event_type=event.event_type,
            case_uid=event.case_uid,
            payload=event.payload,
            entities=event.entities,
            regions=event.regions,
            topics=event.topics,
            severity=event.severity,
            source_event_uid=event.source_event_uid,
            status="processing",
        )
        self._db.add(row)
        await self._db.flush()

        # 3. 规则匹配
        candidates = await self._rule_match(event)

        # 4. 语义匹配
        if self._qdrant and self._llm:
            sem_candidates = await self._semantic_match(event)
            candidates.extend(sem_candidates)

        # 5. 合并去重（同一 user_id 取最高分）
        merged = self._merge_candidates(candidates)

        # 6. 节流 + 投递
        pushed = 0
        for cand in merged:
            throttled = await self._is_throttled(cand.user_id, event.severity)
            status = "throttled" if throttled else "delivered"
            error = None

            if not throttled:
                try:
                    await self._deliver(cand.user_id, event)
                    pushed += 1
                except Exception as exc:
                    status = "failed"
                    error = str(exc)
                    logger.warning("Push failed for user %s: %s", cand.user_id, exc)

            # 7. 记录 push_log
            await self._record_push(
                event_uid=event_uid,
                candidate=cand,
                status=status,
                error=error,
            )

        # 更新事件状态
        row.status = "done"
        row.push_count = pushed
        await self._db.commit()
        return pushed
```

### 3.3 规则匹配

```python
    async def _rule_match(self, event: AegiEvent) -> list[PushCandidate]:
        """遍历 subscriptions 表，找到匹配的订阅。"""
        from aegi_core.db.models.subscription import Subscription

        severity_rank = SEVERITY_RANK.get(event.severity, 1)

        # 构建 OR 条件
        conditions = [
            # case 订阅
            sa.and_(
                Subscription.sub_type == "case",
                Subscription.sub_target == event.case_uid,
            ),
            # global 订阅
            Subscription.sub_type == "global",
        ]
        # entity 订阅
        if event.entities:
            conditions.append(sa.and_(
                Subscription.sub_type == "entity",
                Subscription.sub_target.in_(event.entities),
            ))
        # region 订阅
        if event.regions:
            conditions.append(sa.and_(
                Subscription.sub_type == "region",
                Subscription.sub_target.in_(event.regions),
            ))
        # topic 订阅
        if event.topics:
            conditions.append(sa.and_(
                Subscription.sub_type == "topic",
                Subscription.sub_target.in_(event.topics),
            ))

        stmt = (
            sa.select(Subscription)
            .where(
                Subscription.enabled == True,  # noqa: E712
                Subscription.priority_threshold <= severity_rank,
                sa.or_(*conditions),
            )
        )
        # 事件类型过滤：event_types 为空表示不过滤
        rows = (await self._db.execute(stmt)).scalars().all()

        candidates = []
        for sub in rows:
            # 如果订阅指定了 event_types，检查是否匹配
            if sub.event_types and event.event_type not in sub.event_types:
                continue
            reason = f"{sub.sub_type}:{sub.sub_target}"
            candidates.append(PushCandidate(
                user_id=sub.user_id,
                subscription_uid=sub.uid,
                match_method="rule",
                match_score=1.0,
                match_reason=reason,
            ))
        return candidates
```

### 3.4 语义匹配

```python
    async def _semantic_match(self, event: AegiEvent) -> list[PushCandidate]:
        """用事件摘要 embedding 在 Qdrant expert_profiles 集合中搜索。"""
        # 构建事件摘要文本
        summary = f"[{event.event_type}] {event.payload.get('summary', '')}"
        if event.entities:
            summary += f" entities: {', '.join(event.entities[:5])}"
        if event.topics:
            summary += f" topics: {', '.join(event.topics[:5])}"

        try:
            embedding = await self._llm.embed(summary)
        except Exception:
            logger.warning("Failed to embed event summary, skip semantic match")
            return []

        from aegi_core.infra.qdrant_store import QdrantStore

        # 使用独立集合 "expert_profiles"
        results = await self._qdrant.search(
            query_embedding=embedding,
            limit=20,
            score_threshold=self._semantic_threshold,
        )

        candidates = []
        for hit in results:
            user_id = hit.metadata.get("user_id", "")
            if not user_id:
                continue
            candidates.append(PushCandidate(
                user_id=user_id,
                subscription_uid=hit.metadata.get("subscription_uid"),
                match_method="semantic",
                match_score=hit.score,
                match_reason=f"semantic similarity={hit.score:.3f}",
            ))
        return candidates
```

### 3.5 合并去重 + 节流 + 投递

```python
    @staticmethod
    def _merge_candidates(candidates: list[PushCandidate]) -> list[PushCandidate]:
        """同一 user_id 取最高分的候选。"""
        best: dict[str, PushCandidate] = {}
        for c in candidates:
            existing = best.get(c.user_id)
            if existing is None or c.match_score > existing.match_score:
                best[c.user_id] = c
        return list(best.values())

    async def _is_throttled(self, user_id: str, severity: str) -> bool:
        """检查该用户最近 1 小时的推送数是否超限。critical 不受限。"""
        if severity == "critical":
            return False

        from aegi_core.db.models.push_log import PushLog

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        count = (await self._db.execute(
            sa.select(sa.func.count()).select_from(PushLog).where(
                PushLog.user_id == user_id,
                PushLog.status == "delivered",
                PushLog.created_at >= one_hour_ago,
            )
        )).scalar_one()
        return count >= self._max_push_per_hour

    async def _deliver(self, user_id: str, event: AegiEvent) -> None:
        """调用 dispatch.notify_user() 投递消息。"""
        from aegi_core.openclaw.dispatch import notify_user

        summary = event.payload.get("summary", event.event_type)
        message = f"[{event.severity.upper()}] {summary}"
        if event.case_uid:
            message += f"\n案例: {event.case_uid}"

        await notify_user(user_id, message, label="event_push")

    async def _record_push(
        self,
        *,
        event_uid: str,
        candidate: PushCandidate,
        status: str,
        error: str | None,
    ) -> None:
        """写入 push_log 审计记录。"""
        from aegi_core.db.models.push_log import PushLog

        row = PushLog(
            uid=uuid.uuid4().hex,
            event_uid=event_uid,
            user_id=candidate.user_id,
            subscription_uid=candidate.subscription_uid,
            match_method=candidate.match_method,
            match_score=candidate.match_score,
            match_reason=candidate.match_reason,
            status=status,
            error=error,
        )
        self._db.add(row)
```

---

## 四、现有模块改动点

### 4.1 pipeline_orchestrator.py — run_playbook() 完成后 emit

位置：`services/pipeline_orchestrator.py` 第 186 行（`result.total_duration_ms = ...` 之后）

```python
        result.total_duration_ms = _now_ms() - pipeline_start

        # ── emit pipeline.completed 事件 ──
        from aegi_core.services.event_bus import get_event_bus, AegiEvent
        bus = get_event_bus()
        await bus.emit(AegiEvent(
            event_type="pipeline.completed",
            case_uid=case_uid,
            payload={
                "summary": f"Pipeline '{playbook_name}' completed: "
                           f"{sum(1 for s in result.stages if s.status == 'success')}/{len(result.stages)} stages OK",
                "playbook": playbook_name,
                "duration_ms": result.total_duration_ms,
                "stage_results": {s.stage: s.status for s in result.stages},
            },
            severity="medium",
            source_event_uid=f"pipeline:{case_uid}:{playbook_name}:{result.total_duration_ms}",
        ))

        return result
```

### 4.2 stages/osint_collect.py — 采集完成后 emit

位置：`services/stages/osint_collect.py` 的 `run()` 方法，在构建 `StageResult(status="success", ...)` 之前

```python
        # ── emit osint.collected 事件 ──
        from aegi_core.services.event_bus import get_event_bus, AegiEvent
        bus = get_event_bus()
        await bus.emit(AegiEvent(
            event_type="osint.collected",
            case_uid=ctx.case_uid,
            payload={
                "summary": f"OSINT collected: {result.urls_ingested} URLs, "
                           f"{result.claims_extracted} claims for query '{query}'",
                "query": query,
                "urls_found": result.urls_found,
                "urls_ingested": result.urls_ingested,
                "claims_extracted": result.claims_extracted,
            },
            severity="low",
            source_event_uid=f"osint:{ctx.case_uid}:{query[:64]}:{result.urls_ingested}",
        ))
```

### 4.3 claim_extractor.py — 提取完成后 emit

位置：`services/claim_extractor.py` 的 `extract_from_chunk()` 函数，在 `return valid_claims, action, tool_trace, llm_result` 之前

```python
    # ── emit claim.extracted 事件 ──
    if valid_claims:
        from aegi_core.services.event_bus import get_event_bus, AegiEvent
        bus = get_event_bus()
        await bus.emit(AegiEvent(
            event_type="claim.extracted",
            case_uid=case_uid,
            payload={
                "summary": f"Extracted {len(valid_claims)} claims from chunk {chunk_uid}",
                "chunk_uid": chunk_uid,
                "claim_count": len(valid_claims),
                "claim_uids": [c.uid for c in valid_claims],
            },
            severity="low",
            source_event_uid=f"claim:{case_uid}:{chunk_uid}",
        ))
```

### 4.4 api/main.py — lifespan 中初始化 EventBus + 注册 PushEngine handler

位置：`api/main.py` 的 `lifespan()` 函数，在 `yield` 之前

```python
        # ── 初始化事件总线 + 推送引擎 ──
        from aegi_core.services.event_bus import get_event_bus
        from aegi_core.services.push_engine import create_push_handler
        bus = get_event_bus()
        push_handler = create_push_handler(qdrant=qdrant, llm=None)
        bus.on("*", push_handler)
```

`yield` 之后（shutdown）：

```python
        # ── 优雅关闭事件总线 ──
        from aegi_core.services.event_bus import get_event_bus
        bus = get_event_bus()
        await bus.drain()
```

### 4.5 settings.py — 新增配置项

```python
    # Event-driven push
    event_push_max_per_hour: int = 10
    event_push_semantic_threshold: float = 0.65
    event_push_expert_collection: str = "expert_profiles"
```

---

## 五、push_engine.create_push_handler 工厂

EventBus handler 需要一个 `async def(AegiEvent) -> None` 签名。PushEngine 需要 DB session，所以用工厂函数在每次事件到来时创建独立 session：

```python
# push_engine.py 底部

def create_push_handler(
    *,
    qdrant: Any | None = None,
    llm: Any | None = None,
) -> Callable[[AegiEvent], Awaitable[None]]:
    """创建一个 EventHandler，每次事件到来时获取独立 DB session。"""
    from aegi_core.settings import settings

    async def handler(event: AegiEvent) -> None:
        from aegi_core.db.session import async_session_factory

        async with async_session_factory() as session:
            engine = PushEngine(
                session,
                qdrant=qdrant,
                llm=llm,
                max_push_per_hour=settings.event_push_max_per_hour,
                semantic_threshold=settings.event_push_semantic_threshold,
            )
            pushed = await engine.process_event(event)
            logger.info(
                "PushEngine: event=%s case=%s pushed=%d",
                event.event_type, event.case_uid, pushed,
            )

    handler.__name__ = "push_engine_handler"
    return handler
```

---

## 六、事件流序列图

```
┌──────────────┐    ┌──────────┐    ┌──────────┐    ┌───────────┐    ┌──────────┐
│ Pipeline     │    │ EventBus │    │PushEngine│    │ dispatch  │    │ OpenClaw │
│ Orchestrator │    │          │    │          │    │           │    │ Gateway  │
└──────┬───────┘    └────┬─────┘    └────┬─────┘    └─────┬─────┘    └────┬─────┘
       │                 │               │                │               │
       │ run_playbook()  │               │                │               │
       │ completes       │               │                │               │
       │                 │               │                │               │
       │ emit(pipeline   │               │                │               │
       │ .completed)     │               │                │               │
       │────────────────>│               │                │               │
       │                 │               │                │               │
       │                 │ create_task   │                │               │
       │                 │ (handler)     │                │               │
       │                 │──────────────>│                │               │
       │                 │               │                │               │
       │                 │               │ 1. 去重检查    │               │
       │                 │               │ (source_event  │               │
       │                 │               │  _uid)         │               │
       │                 │               │                │               │
       │                 │               │ 2. 持久化      │               │
       │                 │               │ event_log      │               │
       │                 │               │                │               │
       │                 │               │ 3. 规则匹配    │               │
       │                 │               │ SELECT FROM    │               │
       │                 │               │ subscriptions  │               │
       │                 │               │                │               │
       │                 │               │ 4. 语义匹配    │               │
       │                 │               │ Qdrant search  │               │
       │                 │               │                │               │
       │                 │               │ 5. 合并去重    │               │
       │                 │               │                │               │
       │                 │               │ 6. 节流检查    │               │
       │                 │               │ COUNT push_log │               │
       │                 │               │                │               │
       │                 │               │ 7. 投递        │               │
       │                 │               │───────────────>│               │
       │                 │               │                │ notify_user() │
       │                 │               │                │──────────────>│
       │                 │               │                │               │
       │                 │               │ 8. 记录        │               │
       │                 │               │ push_log       │               │
       │                 │               │                │               │
       │                 │               │ 9. 更新        │               │
       │                 │               │ event_log      │               │
       │                 │               │ status=done    │               │
```

---

## 七、Alembic Migration

文件：`alembic/versions/c3d4e5f6a7b8_add_event_driven_tables.py`

revision ID 沿用项目命名风格（12 位 hex）。

```python
"""Add event-driven tables: subscriptions, event_log, push_log

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscriptions ──
    op.create_table(
        "subscriptions",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False, index=True),
        sa.Column("sub_type", sa.String(16), nullable=False),
        sa.Column("sub_target", sa.String(256), nullable=False, server_default="*"),
        sa.Column("priority_threshold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_types", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("interest_text", sa.Text(), nullable=True),
        sa.Column("embedding_synced", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sub_type_target", "subscriptions", ["sub_type", "sub_target"])

    # ── event_log ──
    op.create_table(
        "event_log",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False, index=True),
        sa.Column("case_uid", sa.String(64), sa.ForeignKey("cases.uid", ondelete="SET NULL"), index=True, nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("entities", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("regions", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("topics", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("source_event_uid", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("push_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )

    # ── push_log ──
    op.create_table(
        "push_log",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column("event_uid", sa.String(64), sa.ForeignKey("event_log.uid", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.String(128), nullable=False, index=True),
        sa.Column("subscription_uid", sa.String(64), nullable=True),
        sa.Column("match_method", sa.String(16), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("match_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("feedback", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("push_log")
    op.drop_table("event_log")
    op.drop_table("subscriptions")
```

---

## 八、Qdrant 专家 Profile 集合

语义匹配需要一个独立的 Qdrant 集合 `expert_profiles`：

- 向量维度：1024（BGE-M3，与 aegi_chunks 一致）
- payload 字段：`user_id`, `subscription_uid`, `interest_text`
- 写入时机：创建/更新 Subscription 时，如果 `interest_text` 非空，调用 LLMClient.embed() 生成 embedding 并 upsert 到 Qdrant
- 集合初始化：在 lifespan 中，与 aegi_chunks 一起 ensure

PushEngine 的语义匹配使用独立的 QdrantStore 实例（collection="expert_profiles"），不与 aegi_chunks 混用。

---

## 九、新增配置项汇总

```python
# settings.py 新增字段
event_push_max_per_hour: int = 10              # 每用户每小时最大推送数
event_push_semantic_threshold: float = 0.65    # 语义匹配阈值
event_push_expert_collection: str = "expert_profiles"  # Qdrant 集合名
```

---

## 十、文件清单

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 新增 | `db/models/subscription.py` | Subscription 模型 |
| 新增 | `db/models/event_log.py` | EventLog 模型 |
| 新增 | `db/models/push_log.py` | PushLog 模型 |
| 新增 | `services/event_bus.py` | EventBus 事件总线 |
| 新增 | `services/push_engine.py` | PushEngine 推送决策引擎 |
| 新增 | `alembic/versions/c3d4e5f6a7b8_...py` | Migration |
| 修改 | `db/models/__init__.py` | 导出新模型 |
| 修改 | `services/pipeline_orchestrator.py:186` | emit pipeline.completed |
| 修改 | `services/stages/osint_collect.py:run()` | emit osint.collected |
| 修改 | `services/claim_extractor.py:return前` | emit claim.extracted |
| 修改 | `api/main.py:lifespan()` | 初始化 EventBus + 注册 handler |
| 修改 | `settings.py` | 新增 3 个配置项 |

---

## 十一、测试计划

### 11.1 单元测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| `test_event_bus.py` | EventBus.on/off/emit/emit_and_wait/drain、通配符、异常隔离 |
| `test_push_engine.py` | 规则匹配（5 种 sub_type）、合并去重、节流逻辑、critical 突破节流 |

### 11.2 集成测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| `test_event_driven_integration.py` | 完整链路：创建 Subscription → emit 事件 → PushEngine 处理 → 验证 push_log 记录 |

### 11.3 测试策略

- EventBus 测试：纯内存，不需要 DB
- PushEngine 测试：使用 conftest.py 中已有的 `async_session` fixture（SQLite async）
- 语义匹配测试：mock QdrantStore + LLMClient.embed
- 投递测试：mock `dispatch.notify_user`
- 节流测试：预插入 push_log 记录，验证节流判断

### 11.4 关键断言

1. 同一 `source_event_uid` 的事件不会被重复处理
2. `priority_threshold` 正确过滤低优先级事件
3. 每小时推送数超限时，非 critical 事件被标记为 `throttled`
4. critical 事件不受节流限制
5. handler 异常不影响其他 handler 执行
6. `drain()` 等待所有 handler 完成后返回
