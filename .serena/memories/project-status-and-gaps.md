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

## 待修复差距（按优先级）

### 高优先级
1. **Alembic 迁移空 pass** — 4 个迁移文件 upgrade/downgrade 都是 pass
   - bc5052692a40_init.py
   - 3f52046a1239_add_cases_and_actions.py
   - 01195e08d027_add_p0_evidence_chain_tables.py
   - a2e59547cc18_add_tool_traces.py
   - 需要对照 db/models/ 填写 op.create_table

2. **fixture 导入 uuid4 不可复现** — fixture_import_service.py 8 处 uuid4
   - 改为 uuid5(NAMESPACE, fixture_key) 确定性生成

3. **anchor_health/drift 占位** — fixture_import_service.py:154 anchor_health={}
   - regression/metrics.py:86 drifted=0 永远返回 0

### 中优先级
4. **pipelines claim_extract 空占位** — anchor_set=[], artifact_version_uid="", evidence_uid=""
   - 需要从 DB 查真实值

5. **orchestration 结果未持久化** — orchestration.py:123 只返回不写 DB
   - 需要写 Action/ToolTrace 到 DB

6. **ontology 版本内存态** — _registry/_case_pins 进程内 dict
   - 需要迁移到 Postgres 表

### 低优先级
7. **gateway stub** — 三个 endpoint 返回 not_implemented
8. **openspec 工件未同步** — 代码已实现但 checkbox 未勾选

## 项目约定
- `# Author: msq`、中文注释、ruff、pytest asyncio_mode=auto
- 架构红线：Evidence-first, SourceClaim-first, Action-only writes
