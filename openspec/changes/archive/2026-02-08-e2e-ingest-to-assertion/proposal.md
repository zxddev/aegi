# Proposal: 端到端集成测试 — ingest → claim_extract → assertion_fuse

## 问题

当前所有 ingestion pipeline 测试都使用 mock ToolClient，无法验证：
- Core ↔ Gateway 的 ASGI 通信是否正确
- doc_parse 返回的 chunks 格式是否与 Chunk 入库逻辑兼容
- claim_extract → assertion_fuse 全链路数据流是否完整

## 方案

新增一个端到端集成测试文件 `test_e2e_ingest_to_assertion.py`，使用真实 Gateway app（通过 ASGI transport 内嵌），
mock 掉 Gateway 对外部 Unstructured API 的 HTTP 调用，验证 ingest → claim_extract → assertion_fuse 全链路。

## 范围

- 新增 1 个测试文件，包含 1 个全链路测试
- 不修改任何生产代码
- 标记 `@requires_postgres`（需要真实数据库）
