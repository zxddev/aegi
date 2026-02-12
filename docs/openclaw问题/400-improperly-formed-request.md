# 400 "Improperly formed request" 问题

## 现象

OpenClaw 长对话（~266条消息）后，所有请求返回 `400 Bad Request: Improperly formed request`，重试也无法恢复。

## 根因

上游 AWS Q API (`generateAssistantResponse`) 不接受纯空格 `" "` 作为消息 content。

kiro-rs 的 converter 在以下场景会生成 `content: " "`：
1. assistant 消息只有 tool_use 没有 text 时，用 `" "` 占位
2. OpenClaw 原始发来的 assistant 消息 content 本身就是 `" "`（只调了工具没说话）
3. 截断历史后 orphan 清理删掉 tool_result，留下空壳 user 消息，填 `" "` 占位

短对话不触发是因为消息少、没有截断、空格消息少。长对话累积大量 tool_use-only 的 assistant 消息，全部 content 为 `" "`。

## 排查过程

1. 加 `dump_request_on_error()` 在 400 时 dump 完整请求体到 `logs/dump_400_*.json`
2. 初始怀疑请求体过大（585KB），加了截断逻辑 → 截到 65KB 还是 400
3. 修复截断导致的 tool_use/tool_result orphan → 还是 400
4. 重置 conversationId（怀疑上游有状态校验）→ 还是 400
5. 用 curl 二分法定位：`{"role":"user","content":" "}` 单条就 400，`content:"x"` 就 200
6. 确认根因：上游不接受纯空格 content

## 修复

`converter.rs` + `handlers.rs`，把所有 `" "` 占位符改为 `"."`：

- `convert_assistant_message()`: tool_use-only 时 content 从 `" "` → `"."`
- `build_history()` 末尾: 遍历所有消息，`content.trim().is_empty()` 的替换为 `"."`
- `convert_request()`: currentMessage 的空 content 也处理
- `fix_orphaned_tool_refs()`: 空 user 消息占位符从 `" "` → `"."`

## 附带改动（截断保护）

虽然根因不是请求体大小，但截断逻辑作为防御性措施保留：

- `truncate_history_if_needed()`: 超过 128KB 时砍历史，保留前2条 + 最近20对
- 截断后重置 `conversationId`（新 UUID）+ 清空 `agentContinuationId`
- `fix_orphaned_tool_refs()`: 清理截断导致的 tool_use/tool_result 孤立引用
- 超大单条消息（>16KB）截断到 4KB

## 相关文件

- `code/temp/kiro.rs/src/anthropic/converter.rs`
- `code/temp/kiro.rs/src/anthropic/handlers.rs`
