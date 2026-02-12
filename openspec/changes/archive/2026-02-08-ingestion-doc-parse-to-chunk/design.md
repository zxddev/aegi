<!-- Author: msq -->

## Decisions

1. doc_parse 返回的每个 chunk 对应一行 Chunk + 一行 Evidence。
2. Chunk.ordinal 按 doc_parse 返回顺序从 0 递增。
3. anchor_set 从 unstructured 的 metadata（page_number/coordinates）映射。
4. Evidence.kind 统一为 `"document_chunk"`，后续可按 element_type 细分。
5. 入库与 doc_parse 调用在同一个 Action 事务内，保证原子性。
6. 不自动触发 claim_extract——返回 chunk_uids，由调用方决定下一步。

## Input / Output Contracts

### ingest 端点

- 输入：`case_uid`（path）、`artifact_version_uid`、`file_url`
- 输出：`{ action_uid, tool_trace_uid, chunk_uids: str[], evidence_uids: str[] }`

### Chunk 映射规则

| unstructured 字段 | Chunk 列 |
|-------------------|----------|
| `text` | `text` |
| 数组下标 | `ordinal` |
| `metadata.page_number` / `metadata.coordinates` | `anchor_set[{type, value}]` |
| 调用参数 | `artifact_version_uid` |

### Evidence 映射规则

| 字段 | 值 |
|------|-----|
| `case_uid` | 调用参数 |
| `artifact_version_uid` | 调用参数 |
| `chunk_uid` | 对应 Chunk.uid |
| `kind` | `"document_chunk"` |

## Error Handling

- doc_parse 失败：现有逻辑不变（记 error trace，不创建 Chunk/Evidence）。
- chunks 为空列表：正常返回空 chunk_uids，不报错。

## Acceptance

1. doc_parse 成功后 Chunk 表行数 == chunks 数组长度。
2. 每个 Chunk 行有对应 Evidence 行。
3. 返回的 chunk_uids 可直接传入 `/pipelines/claim_extract`。
4. Action + ToolTrace 审计完整。
