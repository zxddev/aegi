# 主动推送机制审查报告

**日期**: 2026-02-11
**审查范围**: `src/aegi_core/openclaw/` 目录下的 event_bridge / dispatch / gateway_client / session_manager
**审查目标**: 评估 AEGI 系统主动推送链路的实现完整性

---

## 审查文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `openclaw/event_bridge.py` | 29 | Gateway ChatEvent → AEGI ServerFrame 转换 |
| `openclaw/dispatch.py` | 97 | AEGI → OpenClaw 反向调用（研究分发 + 用户通知） |
| `openclaw/gateway_client.py` | 303 | OpenClaw Gateway WebSocket 客户端 |
| `openclaw/session_manager.py` | 26 | AEGI user_id ↔ OpenClaw session_key 映射 |
| `openclaw/tools.py` | 428 | OpenClaw agent 回调 AEGI 的 REST 端点 |
| `ws/handler.py` | 178 | 前端 WebSocket 端点，桥接 Gateway |
| `ws/protocol.py` | 100 | AEGI WS 协议帧定义 |

---

## 问题 1：event_bridge 能否在检测到新事件时主动推送给专家？

### 结论：纯转换层，不具备主动推送能力

`event_bridge.py` 只有一个函数 `chat_event_to_frame()`（第 9 行），它是一个无状态的映射器，将 OpenClaw Gateway 的 `ChatEvent` 转成 AEGI 前端的 `ServerFrame`。

**调用链路**：仅在 `ws/handler.py:157` 被调用，且仅在用户主动发消息后的 `chat_send` 响应流中使用：

```python
# ws/handler.py:156-159
async for evt in gateway.chat_send(session_key, message, extra_system_prompt=permission_prompt):
    out = chat_event_to_frame(evt)
    if out:
        await _send_frame(ws, out)
```

**缺失项**：
- 无事件源订阅机制（如监听 pipeline 完成、OSINT 采集完成等内部事件）
- 无主动向前端 WS 推送 `Notify` 帧的调用路径
- 不具备"检测新事件"的能力——它只做格式转换，不做事件捕获

---

## 问题 2：dispatch 的事件分发逻辑是否完整？

### 结论：只有"手动触发"的 RPC 调用，没有事件分发系统

`dispatch.py` 提供了三个 async 函数：

| 函数 | 作用 | 实现状态 |
|------|------|----------|
| `dispatch_research()` | 调用 Gateway crawler agent 执行搜索 | 已实现 |
| `notify_user()` | 向用户 session 注入消息（`chat.inject` RPC） | 已实现 |
| `dispatch_and_notify()` | 组合：先研究再通知 | 已实现 |

**关键问题：这三个函数在 `openclaw/` 目录之外没有任何调用者。**

全局搜索 `dispatch_research`、`notify_user`、`dispatch_and_notify` 的结果：

- `openclaw/dispatch.py` — 定义处
- `openclaw/tools.py:408,422` — REST endpoint 包装（`/openclaw/tools/dispatch_research`、`/openclaw/tools/notify_user`）

没有任何 pipeline stage、cron job、service 层代码调用这些函数。唯一的触发方式是外部显式发 HTTP 请求。

**缺失项**：
- 无事件过滤机制（没有 event type 匹配/路由）
- 无优先级队列
- 无去重逻辑（同一事件可能被重复分发）
- 无事件总线 / pub-sub 模式——没有 `EventBus`、`EventEmitter` 或类似抽象
- Pipeline 完成、OSINT 采集完成等内部事件不会自动触发 dispatch

---

## 问题 3：与 OpenClaw Gateway 的 WebSocket 连接实现情况

### 结论：已实现，包含重连机制，但无心跳

`gateway_client.py` 的 `GatewayClient` 实现了完整的 WS 生命周期：

### 已实现

| 功能 | 位置 | 说明 |
|------|------|------|
| 三步握手 | 第 80-115 行 | `connect.challenge` → `connect` → `hello-ok` |
| 持久监听 | 第 139-156 行 | `_listen_loop()` 按 `type` 分发 `res` / `event` |
| 指数退避重连 | 第 158-172 行 | 最多 10 次，最大间隔 60s |
| 优雅关闭 | 第 117-122 行 | cancel listen task + close ws |
| 流式聊天 | 第 216-246 行 | `chat_send()` 返回 `AsyncIterator[ChatEvent]` |
| 消息注入 | 第 262-268 行 | `chat_inject()` 向 session 注入消息 |
| Agent 调用 | 第 270-297 行 | `agent_call()` fire-and-wait 模式 |
| 会话管理 | 第 248-261, 299-302 行 | `chat_history()` / `chat_abort()` / `session_reset()` |

### 缺失项

1. **无心跳 / ping-pong 机制**：如果连接静默断开（如 NAT 超时），只能等到下次发消息时才发现
2. **重连后不恢复 `_chat_queues`**：正在进行的会话在重连后会丢失
3. **重连 10 次失败后静默放弃**：无告警、无回调、无上报
4. **使用已废弃 API**：`_rpc()` 第 132 行使用 `asyncio.get_event_loop().create_future()`，应改为 `asyncio.get_running_loop().create_future()`

### 初始化入口

`api/main.py:59-69` 在 app lifespan 中初始化：

```python
if settings.openclaw_gateway_url:
    gateway = GatewayClient(url=..., token=...)
    await gateway.connect()
    set_gateway_client(gateway)       # → ws/handler.py
    set_gateway(gateway)              # → openclaw/dispatch.py
```

连接失败时降级处理：`gateway = None`，聊天功能禁用。

---

## 问题 4：主动推送链路完整性分析

### 链路环节评估

| 环节 | 状态 | 代码依据 | 说明 |
|------|------|----------|------|
| 事件产生 | 部分实现 | `ws/protocol.py:25-30` 定义了 `NotifyKind`（`pipeline_progress`, `collection_done` 等） | 帧类型已定义，但无自动产生事件的代码 |
| 关联匹配 | 未实现 | — | 没有"哪些用户关注了哪个 case"的订阅关系表，无法判断事件该推给谁 |
| 推送决策 | 未实现 | — | 没有过滤/节流/聚合逻辑，没有"是否值得推送"的判断 |
| 消息投递 | 已实现 | `gateway_client.py:262` `chat_inject()`；`ws/manager.py` `broadcast()` | 可以向指定 session 注入消息，也可以向已连接的前端 WS 发帧 |
| 端到端自动触发 | 未实现 | `dispatch.py:77` `dispatch_and_notify()` 存在但无人调用 | 没有 cron / scheduler / event hook 来自动触发 |

### 链路示意图

```
事件产生              关联匹配           推送决策            消息投递
┌─────────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────────┐
│ Pipeline完成 │    │ 用户订阅  │    │ 过滤/去重/   │    │ chat_inject  │
│ OSINT采集完成│ →  │ Case关注  │ →  │ 节流/优先级  │ →  │ ws_manager   │
│ Cron定时任务 │    │ Topic关注 │    │              │    │ broadcast    │
└─────────────┘    └──────────┘    └──────────────┘    └──────────────┘
     ❌ 缺失           ❌ 缺失          ❌ 缺失            ✅ 已实现
```

---

## 总结

投递管道（最后一公里）已经通了，但整个链路的前三个环节——事件捕获、关联匹配、推送决策——都是空的。当前架构是**被动请求-响应**模式，不是**主动推送**模式。

### 要实现真正的主动推送，需要补齐：

1. **事件总线**（内部 pub/sub）：让 pipeline / OSINT / cron 产生的事件能被统一捕获
2. **订阅关系表**（user ↔ case/topic）：决定事件推给谁
3. **推送决策引擎**（过滤、去重、节流、优先级）：避免消息轰炸
4. **自动触发接入**：将 `dispatch_and_notify()` 接入事件总线的消费端
5. **WS 心跳保活**：确保长连接可靠，避免静默断开

### 风险项

| 风险 | 严重程度 | 说明 |
|------|----------|------|
| 无心跳导致连接静默断开 | 高 | 生产环境 NAT/LB 通常 60-120s 超时 |
| 重连后会话丢失 | 中 | `_chat_queues` 不会恢复，用户需重新发起对话 |
| `asyncio.get_event_loop()` 废弃 | 低 | Python 3.12+ 可能报 DeprecationWarning |
| dispatch 函数无调用者 | 高 | 代码存在但从未被触发，属于死代码 |
