<!-- Author: msq -->

## Why

`tool_parse_service.call_tool_doc_parse` 调用 Gateway doc_parse 后，只记录 ToolTrace 并返回原始 chunks JSON，
没有将解析结果落入 Chunk 表和 Evidence 表。

下游 `claim_extractor.extract_from_chunk` 和 `/pipelines/claim_extract` 都假设 Chunk 行已存在于 DB，
导致 ingestion 链路在 doc_parse → claim_extract 之间断裂。
当前 Chunk 创建仅在 `fixture_import_service` 中存在，无法支撑真实文档的端到端处理。

## What Changes

- 在 `tool_parse_service` 中，doc_parse 成功后将 chunks 写入 Chunk 表 + Evidence 表。
- 新增 `/cases/{case_uid}/pipelines/ingest` 端到端入口：doc_parse → 入库 Chunk/Evidence → 返回 chunk_uids。
- 调用方可用返回的 chunk_uids 触发已有的 `/pipelines/claim_extract`。

## Capabilities

### New Capabilities

- `ingestion-doc-parse-to-chunk`

## Dependencies

- Hard dependency: `foundation-common-contracts`（Action/ToolTrace schema）
- Hard dependency: `automated-claim-extraction-fusion`（下游消费 Chunk 行）
- Service dependency: Gateway `doc_parse` 工具（unstructured 服务）

## Impact

- `code/aegi-core/src/aegi_core/services/tool_parse_service.py`（核心改动）
- `code/aegi-core/src/aegi_core/api/routes/pipelines.py`（新增 ingest 端点）
- `code/aegi-core/tests/test_ingestion_pipeline.py`（新增）
