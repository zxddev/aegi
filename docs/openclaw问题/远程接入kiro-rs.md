# 其他电脑通过 OpenClaw 接入 kiro-rs API

## 前提

kiro-rs 运行在 `192.168.31.50:8990`，已绑定 `0.0.0.0`，局域网可直接访问。

## 1. 验证连通性

在目标电脑上执行：

```bash
curl -s http://192.168.31.50:8990/v1/models \
  -H "x-api-key: sk-kiro-rs-aegi-local-dev" | python3 -m json.tool
```

应返回可用模型列表。

## 2. 配置 OpenClaw

编辑 `~/.openclaw/openclaw.json`：

```json
{
  "models": {
    "mode": "merge",
    "providers": {
      "antihub": {
        "baseUrl": "http://192.168.31.50:8990",
        "apiKey": "sk-kiro-rs-aegi-local-dev",
        "api": "anthropic-messages",
        "models": [
          {
            "id": "claude-opus-4-6",
            "name": "Claude Opus 4.6",
            "reasoning": false,
            "input": ["text"],
            "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
            "contextWindow": 200000,
            "maxTokens": 8192
          },
          {
            "id": "claude-sonnet-4-5-20250929",
            "name": "Claude Sonnet 4.5",
            "reasoning": false,
            "input": ["text"],
            "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
            "contextWindow": 200000,
            "maxTokens": 8192
          }
        ]
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
  "gateway": {
    "mode": "local",
    "auth": { "mode": "token", "token": "local-dev" }
  }
}
```

## 3. 可用模型

| 模型 ID | 说明 |
|---------|------|
| `claude-opus-4-6` | Opus 4.6 |
| `claude-opus-4-6-thinking` | Opus 4.6 + extended thinking |
| `claude-sonnet-4-5-20250929` | Sonnet 4.5 |
| `claude-sonnet-4-5-20250929-thinking` | Sonnet 4.5 + thinking |
| `claude-haiku-4-5-20251001` | Haiku 4.5 |
| `claude-haiku-4-5-20251001-thinking` | Haiku 4.5 + thinking |
| `claude-opus-4-5-20251101` | Opus 4.5 |
| `claude-opus-4-5-20251101-thinking` | Opus 4.5 + thinking |

在 OpenClaw 配置中引用时加 provider 前缀：`antihub/claude-opus-4-6`

## 4. 注意事项

- IP `192.168.31.50` 是当前局域网地址，如果变动需要更新配置
- API Key 是固定的 `sk-kiro-rs-aegi-local-dev`，无鉴权意义，仅做格式校验
- thinking 模型需要在 OpenClaw 模型配置中设 `"reasoning": true`
- 长对话（>500KB 请求体）会触发历史截断，不影响使用
