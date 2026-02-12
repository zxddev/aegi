# Design: Archive-first Pipeline

## 架构

```
POST /pipelines/archive_and_ingest
  → tool_archive_service.call_tool_archive_url()
  → 创建 ArtifactIdentity + ArtifactVersion
  → tool_parse_service.call_tool_doc_parse()
  → 返回 chunk_uids + evidence_uids
```

## 验收标准

- [x] 端点正常返回 artifact_version_uid + chunk_uids
- [x] archive 失败返回 502 ProblemDetail
- [x] 9/9 测试通过
- [x] ruff clean
