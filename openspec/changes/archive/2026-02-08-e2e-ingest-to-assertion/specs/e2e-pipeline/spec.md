<!-- Author: msq -->

## ADDED Requirements

### Requirement: E2E test MUST verify full ingest-to-assertion data flow
端到端测试 MUST 验证 ingest → claim_extract → assertion_fuse 全链路数据流完整性。

#### Scenario: Full pipeline produces assertions
- **WHEN** 执行 ingest（mock Gateway）→ claim_extract（mock LLM）→ assertion_fuse
- **THEN** Chunk、SourceClaim、Assertion 表均有正确记录

### Requirement: Gateway integration MUST use ASGI transport
测试 MUST 通过 ASGI transport 内嵌真实 Gateway app，验证 Core ↔ Gateway 通信。

#### Scenario: Real gateway app processes doc_parse
- **WHEN** ingest 调用 doc_parse
- **THEN** 请求经过真实 Gateway 路由处理，仅 mock 外部 HTTP 调用
