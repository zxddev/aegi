"""OpenClaw Gateway WebSocket 客户端。

和 Gateway 保持一条持久连接，以 ``backend`` 模式运行。
所有用户消息通过 ``sessionKey`` 多路复用。

用法::

    client = GatewayClient(url="ws://localhost:4800", token="xxx")
    await client.connect()

    async for chunk in client.chat_send("agent:team:gateway:alice", "hello"):
        print(chunk)  # ChatEvent 对象

    await client.close()
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator
from uuid import uuid4

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1


# --- 从 Gateway 收到的事件类型 ---


class ChatEvent:
    """``chat.send`` 运行中的单个事件。"""

    __slots__ = (
        "run_id",
        "session_key",
        "state",
        "text",
        "tool",
        "tool_status",
        "error",
    )

    def __init__(
        self,
        *,
        run_id: str,
        session_key: str,
        state: str,
        text: str = "",
        tool: str = "",
        tool_status: str = "",
        error: str = "",
    ):
        self.run_id = run_id
        self.session_key = session_key
        self.state = state
        self.text = text
        self.tool = tool
        self.tool_status = tool_status
        self.error = error


# --- 客户端 ---


class GatewayClient:
    """单连接异步 Gateway WebSocket 客户端。"""

    def __init__(self, url: str, token: str):
        self._url = url
        self._token = token
        self._ws: ClientConnection | None = None
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._chat_queues: dict[str, asyncio.Queue[ChatEvent | None]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._closed = False

    # -- 生命周期 -------------------------------------------------------------

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._url, max_size=16 * 1024 * 1024)
        # 等待 connect.challenge
        raw = await self._ws.recv()
        challenge = json.loads(raw)
        if challenge.get("event") != "connect.challenge":
            raise RuntimeError(f"unexpected first frame: {challenge}")

        # 发送 connect
        connect_id = uuid4().hex
        await self._send(
            {
                "type": "req",
                "id": connect_id,
                "method": "connect",
                "params": {
                    "minProtocol": PROTOCOL_VERSION,
                    "maxProtocol": PROTOCOL_VERSION,
                    "client": {
                        "id": "gateway-client",
                        "displayName": "AEGI Backend",
                        "version": "0.1.0",
                        "platform": "linux",
                        "mode": "backend",
                    },
                    "auth": {"token": self._token},
                },
            }
        )

        # 等待 hello-ok
        raw = await self._ws.recv()
        hello = json.loads(raw)
        if hello.get("type") != "hello-ok":
            raise RuntimeError(f"handshake failed: {hello}")

        logger.info("Gateway connected, protocol=%s", hello.get("protocol"))
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def close(self) -> None:
        self._closed = True
        if self._listen_task:
            self._listen_task.cancel()
        if self._ws:
            await self._ws.close()

    # -- RPC 辅助方法 -------------------------------------------------------

    async def _send(self, frame: dict) -> None:
        assert self._ws is not None
        await self._ws.send(json.dumps(frame))

    async def _rpc(self, method: str, params: dict) -> dict:
        req_id = uuid4().hex
        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        await self._send(
            {"type": "req", "id": req_id, "method": method, "params": params}
        )
        return await fut

    # -- 监听循环 -----------------------------------------------------------

    async def _listen_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                frame = json.loads(raw)
                ftype = frame.get("type")

                if ftype == "res":
                    self._handle_response(frame)
                elif ftype == "event":
                    self._handle_event(frame)
                # 忽略 tick 等帧
        except websockets.ConnectionClosed:
            if not self._closed:
                logger.warning("Gateway connection lost, scheduling reconnect")
                asyncio.create_task(self._reconnect())
        except asyncio.CancelledError:
            pass

    async def _reconnect(self) -> None:
        """指数退避重连。"""
        delay = 1.0
        for attempt in range(10):
            if self._closed:
                return
            logger.info("Reconnect attempt %d in %.1fs", attempt + 1, delay)
            await asyncio.sleep(delay)
            try:
                await self.connect()
                logger.info("Reconnected to Gateway")
                return
            except Exception:
                logger.warning("Reconnect attempt %d failed", attempt + 1)
                delay = min(delay * 2, 60.0)

    def _handle_response(self, frame: dict) -> None:
        req_id = frame.get("id", "")
        fut = self._pending.pop(req_id, None)
        if fut and not fut.done():
            fut.set_result(frame)

    def _handle_event(self, frame: dict) -> None:
        event = frame.get("event")
        if event != "chat":
            return
        payload = frame.get("payload", {})
        session_key = payload.get("sessionKey", "")
        run_id = payload.get("runId", "")
        state = payload.get("state", "")

        q = self._chat_queues.get(run_id)
        if not q:
            return

        msg = payload.get("message", {})
        text = ""
        if msg:
            content = msg.get("content", [])
            if isinstance(content, list):
                text = "".join(
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )

        evt = ChatEvent(
            run_id=run_id,
            session_key=session_key,
            state=state,
            text=text,
            error=payload.get("errorMessage", ""),
        )

        q.put_nowait(evt)
        if state in ("final", "error"):
            q.put_nowait(None)  # sentinel

    # -- 公开 API -----------------------------------------------------------

    async def chat_send(
        self, session_key: str, message: str, *, extra_system_prompt: str = ""
    ) -> AsyncIterator[ChatEvent]:
        """发送聊天消息，流式返回事件。"""
        idem = uuid4().hex
        q: asyncio.Queue[ChatEvent | None] = asyncio.Queue()
        # 先用 idem 注册队列；拿到 RPC 响应后换成 runId
        self._chat_queues[idem] = q

        try:
            params: dict[str, Any] = {
                "sessionKey": session_key,
                "message": message,
                "idempotencyKey": idem,
            }
            if extra_system_prompt:
                params["extraSystemPrompt"] = extra_system_prompt
            res = await self._rpc("chat.send", params)
            # Gateway 返回自己的 runId — 把队列重新注册到那个 key 下
            run_id = res.get("payload", {}).get("runId", idem)
            if run_id != idem:
                self._chat_queues[run_id] = q
                self._chat_queues.pop(idem, None)

            while True:
                evt = await q.get()
                if evt is None:
                    break
                yield evt
        finally:
            self._chat_queues.pop(idem, None)
            if "run_id" in dir():
                self._chat_queues.pop(run_id, None)

    async def chat_history(
        self, session_key: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """获取会话聊天历史。"""
        res = await self._rpc(
            "chat.history", {"sessionKey": session_key, "limit": limit}
        )
        payload = res.get("payload", {})
        return payload.get("messages", [])

    async def chat_abort(self, session_key: str, run_id: str | None = None) -> bool:
        """中止正在运行的聊天。"""
        params: dict[str, Any] = {"sessionKey": session_key}
        if run_id:
            params["runId"] = run_id
        res = await self._rpc("chat.abort", params)
        return res.get("payload", {}).get("aborted", False)

    async def chat_inject(
        self, session_key: str, message: str, label: str = ""
    ) -> bool:
        """往会话里注入一条消息（比如 AEGI 分析结果）。"""
        params: dict[str, Any] = {"sessionKey": session_key, "message": message}
        if label:
            params["label"] = label
        res = await self._rpc("chat.inject", params)
        return res.get("payload", {}).get("ok", False)

    async def agent_call(
        self,
        message: str,
        *,
        agent_id: str = "team",
        session_key: str | None = None,
        extra_system_prompt: str = "",
        timeout: int = 120,
    ) -> dict[str, Any]:
        """发起 agent 调用，等待结果返回。"""
        idem = uuid4().hex
        params: dict[str, Any] = {
            "message": message,
            "agentId": agent_id,
            "idempotencyKey": idem,
            "timeout": timeout,
        }
        if session_key:
            params["sessionKey"] = session_key
        if extra_system_prompt:
            params["extraSystemPrompt"] = extra_system_prompt

        res = await self._rpc("agent", params)
        run_id = res.get("payload", {}).get("runId", idem)

        # 等待完成
        wait_res = await self._rpc(
            "agent.wait", {"runId": run_id, "timeoutMs": timeout * 1000}
        )
        return wait_res.get("payload", {})

    async def session_reset(self, session_key: str) -> bool:
        """重置会话（清空上下文）。"""
        res = await self._rpc("sessions.reset", {"key": session_key})
        return res.get("payload", {}).get("ok", False)
