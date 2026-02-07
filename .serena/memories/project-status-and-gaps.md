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

## 待修复差距（按优先级）— 2026-02-07 更新

### 高优先级
1. ~~Gateway 三个 endpoint 全是 stub~~ ✅ — archive_url 用 httpx 实现, meta_search/doc_parse 降级模式
2. **Core ToolClient 只有 archive_url()** — 缺 meta_search() 和 doc_parse()
3. **Chat EvidenceCitation 缺 artifact_version_uid** — 需要二跳才能回源
4. **外部 HTTP 调用零 retry/backoff** — LLMClient/ToolClient 无重试

### 中优先级
5. **Gateway tool_trace 纯内存** — TOOL_TRACES 是进程内 list，重启丢失
6. **Ontology 版本 write-through 但 read 仍内存** — _registry/_case_pins 是进程内 dict
   - 已有 load_from_db + save_to_db，但多进程不一致
7. **Assertion.value 永远 {}** — fixture_import 写入 value={}，claim_extractor 也未填充

### 已修复（不再是问题）
- ~~Alembic 迁移空壳~~ — 只有 init 是 pass，其余 6 个迁移都有真实 DDL
- ~~fixture uuid4 不可复现~~ — 已改为 uuid5 确定性生成
- ~~anchor_health 占位~~ — fixture_import 已计算 located/drifted
- ~~drift_rate 永远 0~~ — metrics.py 已有真实漂移计算
- ~~orchestration 结果未持久化~~ — orchestration.py 已写 Action + ToolTrace 到 DB

## 项目约定
- `# Author: msq`、中文注释、ruff、pytest asyncio_mode=auto
- 架构红线：Evidence-first, SourceClaim-first, Action-only writes