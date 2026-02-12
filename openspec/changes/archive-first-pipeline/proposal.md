# Proposal: Archive-first Pipeline

## 问题
当前 ingest 需要预先手动创建 ArtifactVersion，archive_url 和 doc_parse 是独立调用。

## 方案
新增 `archive_and_ingest` 端点，一站式完成：archive_url → 自动创建 ArtifactIdentity/Version → doc_parse 入库。

## 范围
- 新增 POST /cases/{case_uid}/pipelines/archive_and_ingest
- 新增 2 个测试
