# 当前项目状态与待修复差距

## 测试状态
- aegi-core: 212 passed（1 个 flaky timeout: test_llm_invoke）
- aegi-mcp-gateway: 10 passed
- ruff check/format: clean

## 最近完成
- 修复 25 个测试失败（asyncpg event loop + lru_cache 污染）
- Neo4jStore 改用 anyio.to_thread.run_sync 不阻塞事件循环
- kg_mapper.build_graph 返回 BuildGraphResult dataclass（替代 tuple union）
- build_from_assertions API 写入 Neo4j
- 实体消歧服务 + API + Neo4j SAME_AS
- minio exists() 只捕获 S3Error
- chat.py 语义检索降级加 warning 日志
- narrative_builder DRY 重构

## 待修复差距（按优先级）— 2026-02-07 21:07 更新

### 仍存在
1. **Gateway 默认端口不匹配** — settings.py 默认 8601/8603，ports.md 写 8701/8703
2. **Assertion.value 永远 {}** — fixture_import 写入 value={}
3. **Ontology 版本读取仍依赖内存 dict** — _registry/_case_pins 多进程不一致
4. **LLMClient.embed() 无 retry** — invoke 有 _post_with_retry，embed 直接裸调

### 已修复（2026-02-07 确认）
- Gateway 三个 endpoint 已接入真实服务（SearxNG/httpx fetch/Unstructured）
- ToolClient 已补齐 meta_search() + doc_parse() + 通用 _post retry
- EvidenceCitation 已加 artifact_version_uid 字段
- chat.py 构建 citation 时已填入 sc.artifact_version_uid
- LLMClient.invoke 已有 _post_with_retry（3次 exponential backoff）
- Gateway tool_trace 已加 JSONL 文件持久化（AEGI_GATEWAY_TRACE_DIR）

## 项目约定
- `# Author: msq`、中文注释、ruff、pytest asyncio_mode=auto
- 架构红线：Evidence-first, SourceClaim-first, Action-only writes