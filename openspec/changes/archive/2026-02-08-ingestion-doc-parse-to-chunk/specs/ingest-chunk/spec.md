<!-- Author: msq -->

## ADDED Requirements

### Requirement: doc_parse MUST persist chunks to database
call_tool_doc_parse 成功后 MUST 将每个 chunk 写入 Chunk 表和 Evidence 表。

#### Scenario: Chunks persisted after doc_parse
- **WHEN** doc_parse 返回 N 个 chunks
- **THEN** Chunk 表新增 N 行，Evidence 表新增 N 行，action.outputs 包含 chunk_uids

### Requirement: Anchor set MUST map unstructured metadata
anchor_set MUST 映射 page_number、coordinates、filename、languages 字段。

#### Scenario: Metadata mapped to anchor_set
- **WHEN** chunk metadata 包含 page_number 和 filename
- **THEN** anchor_set 包含对应的 page 和 filename 条目

### Requirement: Ingest endpoint MUST return structured error on failure
/pipelines/ingest 失败时 MUST 返回 HTTP 502 和 {ok: false, error: message} 格式。

#### Scenario: Gateway error returns 502
- **WHEN** ToolClient.doc_parse 抛出异常
- **THEN** 返回 502 和统一错误格式
