"""端到端集成测试：主动推送完整闭环。

场景：创建 case → 创建 subscription → 触发 pipeline.completed 事件
     → PushEngine 处理 → event_log + push_log 写入验证。

不依赖真实 LLM，mock dispatch.notify_user 避免调用 OpenClaw Gateway。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import requires_postgres

from aegi_core.db.models.event_log import EventLog
from aegi_core.db.models.push_log import PushLog
from aegi_core.db.models.subscription import Subscription
from aegi_core.db.session import ENGINE
from aegi_core.services.event_bus import AegiEvent, get_event_bus, reset_event_bus
from aegi_core.services.push_engine import PushEngine

pytestmark = requires_postgres


@pytest.fixture(autouse=True)
def _reset_bus():
    reset_event_bus()
    yield
    reset_event_bus()


async def _create_case(session: AsyncSession) -> str:
    """直接写 DB 创建 case，避免依赖 API 路由。"""
    from aegi_core.db.models.case import Case

    case_uid = f"case_{uuid.uuid4().hex[:8]}"
    session.add(Case(uid=case_uid, title="Push E2E test"))
    await session.flush()
    return case_uid


async def _create_subscription(
    session: AsyncSession, *, user_id: str, case_uid: str
) -> str:
    """创建一个订阅该 case 的 subscription。"""
    sub_uid = f"sub_{uuid.uuid4().hex[:8]}"
    session.add(
        Subscription(
            uid=sub_uid,
            user_id=user_id,
            sub_type="case",
            sub_target=case_uid,
            priority_threshold=0,
            event_types=[],
            enabled=True,
        )
    )
    await session.flush()
    return sub_uid


@pytest.mark.asyncio
async def test_proactive_push_full_loop():
    """完整闭环：case + subscription + event → PushEngine → event_log + push_log。"""

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        # 1. 创建 case 和 subscription
        case_uid = await _create_case(session)
        sub_uid = await _create_subscription(
            session, user_id="expert_alice", case_uid=case_uid
        )
        await session.commit()

    # 2. 构造 pipeline.completed 事件
    event = AegiEvent(
        event_type="pipeline.completed",
        case_uid=case_uid,
        payload={"summary": "ingest pipeline done", "stage_count": 3},
        severity="medium",
    )

    # 3. 用真实 DB session 运行 PushEngine，mock notify_user
    with patch(
        "aegi_core.openclaw.dispatch.notify_user", new_callable=AsyncMock
    ) as mock_notify:
        mock_notify.return_value = True

        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            engine = PushEngine(session, max_push_per_hour=100)
            pushed = await engine.process_event(event)

    # 4. 断言推送成功
    assert pushed == 1
    mock_notify.assert_awaited_once()
    call_args = mock_notify.call_args
    assert call_args[0][0] == "expert_alice"  # user_id
    assert case_uid in call_args[0][1]  # message 包含 case_uid

    # 5. 验证 event_log
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        el_row = (
            await session.execute(
                sa.select(EventLog).where(
                    EventLog.source_event_uid == event.source_event_uid
                )
            )
        ).scalar_one()
        assert el_row.event_type == "pipeline.completed"
        assert el_row.case_uid == case_uid
        assert el_row.status == "done"
        assert el_row.push_count == 1

        # 6. 验证 push_log
        pl_row = (
            await session.execute(
                sa.select(PushLog).where(PushLog.event_uid == el_row.uid)
            )
        ).scalar_one()
        assert pl_row.status == "delivered"
        assert pl_row.match_method == "rule"
        assert case_uid in pl_row.match_reason
        assert pl_row.user_id == "expert_alice"
        assert pl_row.subscription_uid == sub_uid


@pytest.mark.asyncio
async def test_proactive_push_via_event_bus():
    """通过 EventBus emit_and_wait 触发 PushEngine handler 的完整链路。"""

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        case_uid = await _create_case(session)
        await _create_subscription(session, user_id="expert_bob", case_uid=case_uid)
        await session.commit()

    event = AegiEvent(
        event_type="pipeline.completed",
        case_uid=case_uid,
        payload={"summary": "full chain via bus"},
        severity="high",
    )

    # 注册 push handler 到 EventBus，mock notify_user
    with patch(
        "aegi_core.openclaw.dispatch.notify_user", new_callable=AsyncMock
    ) as mock_notify:
        mock_notify.return_value = True

        from aegi_core.services.push_engine import create_push_handler

        handler = create_push_handler()
        bus = get_event_bus()
        bus.on("pipeline.completed", handler)

        await bus.emit_and_wait(event)

    # 验证 event_log + push_log
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        el_row = (
            await session.execute(
                sa.select(EventLog).where(
                    EventLog.source_event_uid == event.source_event_uid
                )
            )
        ).scalar_one()
        assert el_row.event_type == "pipeline.completed"
        assert el_row.status == "done"

        pl_row = (
            await session.execute(
                sa.select(PushLog).where(PushLog.event_uid == el_row.uid)
            )
        ).scalar_one()
        assert pl_row.status == "delivered"
        assert pl_row.match_method == "rule"
        assert case_uid in pl_row.match_reason
        assert pl_row.user_id == "expert_bob"

    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_push_when_no_subscription():
    """没有匹配的 subscription 时，不应产生 push_log。"""

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        case_uid = await _create_case(session)
        await session.commit()

    event = AegiEvent(
        event_type="pipeline.completed",
        case_uid=case_uid,
        payload={"summary": "no subscriber"},
        severity="medium",
    )

    with patch(
        "aegi_core.openclaw.dispatch.notify_user", new_callable=AsyncMock
    ) as mock_notify:
        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            engine = PushEngine(session, max_push_per_hour=100)
            pushed = await engine.process_event(event)

    assert pushed == 0
    mock_notify.assert_not_awaited()

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        el_row = (
            await session.execute(
                sa.select(EventLog).where(
                    EventLog.source_event_uid == event.source_event_uid
                )
            )
        ).scalar_one()
        assert el_row.status == "done"
        assert el_row.push_count == 0

        pl_count = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(PushLog)
                .where(PushLog.event_uid == el_row.uid)
            )
        ).scalar_one()
        assert pl_count == 0
