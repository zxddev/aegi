# Design: 端到端集成测试

## 架构

```
Test → Core App (ASGI) → call_tool_doc_parse → ToolClient → Gateway App (ASGI)
                                                                ↓
                                                    Gateway doc_parse endpoint
                                                                ↓
                                                    httpx.AsyncClient.get(file_url) ← mock
                                                    httpx.AsyncClient.post(unstructured) ← mock
```

## 测试策略

1. 内嵌 Gateway app 作为 ToolClient 的后端（同 test_tool_trace_gateway_integration.py 模式）
2. mock Gateway 内部的 httpx 调用（下载文件 + 调用 Unstructured API），返回预设的 elements
3. mock LLM 后端，让 claim_extract 返回可控的 claims
4. 验证全链路：Chunk 入库 → SourceClaim 入库 → Assertion 入库

## 验收标准

- [x] 测试通过 `pytest tests/test_e2e_ingest_to_assertion.py -v`
- [x] Chunk 表有记录且 text 与 mock elements 一致
- [x] SourceClaim 表有记录
- [x] Assertion 表有记录
- [x] ruff clean
