<!-- Author: msq -->

## 1. tool_parse_service 入库逻辑

- [x] 1.1 在 `call_tool_doc_parse` 成功分支中，遍历 `resp["chunks"]` 创建 Chunk + Evidence 行
- [x] 1.2 从 unstructured metadata 映射 anchor_set（page_number/coordinates）
- [x] 1.3 将 chunk_uids / evidence_uids 写入 action.outputs

## 2. API 端点

- [x] 2.1 在 `api/routes/pipelines.py` 新增 `POST /cases/{case_uid}/pipelines/ingest`
- [x] 2.2 请求体：`artifact_version_uid` + `file_url`
- [x] 2.3 响应体：`action_uid` + `tool_trace_uid` + `chunk_uids[]` + `evidence_uids[]`

## 3. 测试

- [x] 3.1 新增 `test_ingestion_pipeline.py`：mock doc_parse → 验证 Chunk/Evidence 入库
- [x] 3.2 验证空 chunks 场景返回空列表
- [x] 3.3 验证 chunk_uids 可传入 claim_extract（集成路径）

## 4. 验收

- [x] 4.1 Chunk 行数 == doc_parse chunks 长度
- [x] 4.2 每个 Chunk 有对应 Evidence
- [x] 4.3 Action.outputs 包含 chunk_uids
- [x] 4.4 ruff check + ruff format clean
- [x] 4.5 全量 pytest 通过（202 passed aegi-core, 11 passed aegi-mcp-gateway）