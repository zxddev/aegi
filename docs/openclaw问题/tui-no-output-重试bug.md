# OpenClaw TUI "(no output)" 重试 Bug

## 问题描述

OpenClaw TUI 连接 kiro.rs（自定义 Anthropic API 代理）时，如果第一次 LLM 请求失败（如 token 过期返回 502），重试成功后 TUI 仍然显示 "(no output)"。

## 环境

- OpenClaw: 2026.2.6-3
- Gateway: ws://127.0.0.1:18789（local 模式）
- LLM 后端: kiro.rs (http://localhost:8990)，`api: "anthropic-messages"`
- 模型: claude-opus-4-6

## 配置

`~/.openclaw/openclaw.json`:

```json
{
  "models": {
    "mode": "merge",
    "providers": {
      "antihub": {
        "baseUrl": "http://localhost:8990",
        "apiKey": "sk-kiro-rs-aegi-local-dev",
        "api": "anthropic-messages",
        "models": [{
          "id": "claude-opus-4-6",
          "name": "Claude Opus 4.6 via AntiHub",
          "reasoning": false,
          "input": ["text"],
          "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
          "contextWindow": 200000,
          "maxTokens": 8192
        }]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": { "primary": "antihub/claude-opus-4-6" },
      "maxConcurrent": 4,
      "subagents": { "maxConcurrent": 8 }
    }
  },
  "gateway": { "mode": "local", "auth": { "mode": "token", "token": "local-dev" } }
}
```

## 根因分析

### 事件时间线（从 gateway 日志）

1. `00:31:34` — embedded run agent start（第一次尝试）
2. `00:32:23` — 第一次失败：kiro.rs 返回 `502 所有凭据均无法获取有效 Token`
3. `00:32:23` — embedded run agent end（第一次结束）
4. `00:32:25` — embedded run agent start（重试，**同一个 runId**）
5. `00:32:45-48` — 重试成功，所有 SSE 事件正常接收
6. `00:32:48` — embedded run done: aborted=false
7. TUI 显示 "(no output)"

### 代码层面原因

涉及三个关键文件：

**1. `tui-event-handlers.ts` (行 91-98)**

```typescript
if (finalizedRuns.has(evt.runId)) {
  if (evt.state === "delta") {
    return;  // 丢弃已完成 run 的 delta 事件
  }
  if (evt.state === "final") {
    return;  // 丢弃已完成 run 的 final 事件
  }
}
```

**2. `tui-stream-assembler.ts`**

- `finalize(runId)` 被调用后，会从 map 中删除该 run 的状态
- 第一次失败时 finalize 被调用，输出为空

**3. `tui-formatters.ts`**

```typescript
export function resolveFinalAssistantText(params) {
  const finalText = params.finalText ?? "";
  if (finalText.trim()) return finalText;
  const streamedText = params.streamedText ?? "";
  if (streamedText.trim()) return streamedText;
  return "(no output)";  // finalText 和 streamedText 都为空时
}
```

### 完整流程

1. 第一次请求失败 → TUI 收到 error/final 事件
2. `streamAssembler.finalize()` 被调用 → 返回 "(no output)" → runId 加入 `finalizedRuns`
3. Agent runner 用**同一个 runId** 发起重试 → kiro.rs 成功返回流式数据
4. TUI 收到新的 delta 事件，但因为 runId 已在 `finalizedRuns` 中，**全部被静默丢弃**
5. 用户看到的始终是第一次失败的 "(no output)"

## 解决方案

### 临时方案（推荐）

确保 kiro.rs token 有效，第一次请求就成功，不触发重试：
- 重启 gateway 清除旧状态
- 确认 kiro.rs credentials 未过期

### 根本方案（需改 OpenClaw 源码）

以下任一方式可修复：
- 重试时使用不同的 runId
- 重试开始时从 `finalizedRuns` 中移除旧 runId
- 收到新 delta 事件时允许 "复活" 已完成的 run

## 诊断命令

```bash
# 检查 gateway 状态
openclaw status

# 检查模型可用性
openclaw models status

# 实时查看日志
openclaw logs --follow

# 运行诊断
openclaw doctor

# 启用详细日志（在 openclaw.json 中添加）
# "logging": { "level": "trace", "consoleLevel": "debug" }
```

## 验证 kiro.rs 是否正常

```bash
curl -s http://localhost:8990/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-kiro-rs-aegi-local-dev" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-opus-4-6","max_tokens":50,"stream":true,"messages":[{"role":"user","content":"Say hi"}]}'
```

正常应返回完整的 SSE 事件序列：message_start → content_block_start → content_block_delta → content_block_stop → message_delta → message_stop
