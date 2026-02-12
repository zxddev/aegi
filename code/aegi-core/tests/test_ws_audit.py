"""WS 聊天审计日志测试。"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_audit_chat_send():
    """_audit_chat_send 创建一条 Action 记录。"""
    from aegi_core.ws.handler import _audit_chat_send

    mock_session = AsyncMock()
    mock_engine = MagicMock()

    with (
        patch("aegi_core.ws.handler.get_engine", return_value=mock_engine),
        patch("aegi_core.ws.handler.AsyncSession") as MockAsyncSession,
    ):
        # 让 context manager 返回 mock session
        MockAsyncSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        MockAsyncSession.return_value.__aexit__ = AsyncMock(return_value=False)

        await _audit_chat_send("user_123", "hello world", "msg_1")

        # 验证 Action 已添加
        mock_session.add.assert_called_once()
        action = mock_session.add.call_args[0][0]
        assert action.action_type == "ws.chat_send"
        assert action.actor_id == "user_123"
        assert action.inputs["message"] == "hello world"
        assert action.case_uid is None
        mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_chat_send_truncates_long_message():
    """审计日志截断超过 500 字符的消息。"""
    from aegi_core.ws.handler import _audit_chat_send

    mock_session = AsyncMock()
    mock_engine = MagicMock()
    long_msg = "x" * 1000

    with (
        patch("aegi_core.ws.handler.get_engine", return_value=mock_engine),
        patch("aegi_core.ws.handler.AsyncSession") as MockAsyncSession,
    ):
        MockAsyncSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        MockAsyncSession.return_value.__aexit__ = AsyncMock(return_value=False)

        await _audit_chat_send("user_1", long_msg, "msg_2")

        action = mock_session.add.call_args[0][0]
        assert len(action.inputs["message"]) == 500
