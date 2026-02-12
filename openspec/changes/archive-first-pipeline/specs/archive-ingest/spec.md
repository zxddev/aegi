<!-- Author: msq -->

## ADDED Requirements

### Requirement: archive_and_ingest MUST chain archive → artifact → ingest
端点 MUST 依次执行 archive_url、创建 ArtifactVersion、doc_parse，返回完整结果。

#### Scenario: Full archive-ingest pipeline
- **WHEN** 调用 archive_and_ingest 传入 url
- **THEN** 返回 artifact_version_uid、chunk_uids、evidence_uids

### Requirement: Archive failure MUST return ProblemDetail
archive_url 失败时 MUST 返回 502 ProblemDetail，不得返回非标准格式。

#### Scenario: Archive error returns 502
- **WHEN** archive_url 抛出异常
- **THEN** 返回 502 且 error_code = "gateway_error"
