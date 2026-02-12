<!-- Author: msq -->

# Changelog

## [0.4.0] — 2026-02-11

### Phase 4: OSINT 采集管道
- CollectionJob 数据模型 + Alembic 迁移
- OSINTCollector 全流程：SearXNG 搜索 → httpx/Playwright 抓取 → HTML 解析 → SHA256 去重 → 入库 → 声明提取
- 来源可信度评分（规则引擎，域名分级）
- OSINT pipeline stage + osint_deep playbook
- 采集 API 6 端点（CRUD + 触发 + 搜索预览）
- WebSocket 连接管理器 + 采集完成推送

### Phase 5: 流式传输与实时进度
- LLMClient.invoke_stream() SSE 流式输出
- Pipeline 进度追踪器（内存 + asyncio.Event 订阅）
- SSE 端点：pipeline 运行流、运行订阅、chat 流式
- PipelineOrchestrator on_progress 回调
- WS 协议扩展：pipeline_progress + collection_done

### 补全
- 多视角分析 API 端点（persona_generator 接入）
- WS 聊天审计日志（复用 Action 模型，case_uid 改为 nullable）
- 错误处理增强：开发阶段不降级，直接暴露错误
- OSINT 集成测试（真实 SearXNG）
- openspec 归档清理

## [0.3.0] — 2026-02-08

### 质量修复（6/6 完成）

- **#1 KG build produces nothing** — GraphRAG entity extraction pipeline (`graphrag_pipeline.py`)
- **#2 Forecast probabilities all 0.0** — `causal_reasoner`: 单 assertion 假设 `consistency_score` 从 0.0 修正为 1.0（无矛盾 = 一致）
- **#3 Narrative doesn't link assertions** — `narrative_builder`: 通过 `source_claim_uid → assertion_uid` 反向索引填充 `assertion_uids`
- **#4 Hypothesis intelligence too sparse** — `hypothesis_engine`: LLM structured output ACH 分析替代关键词规则引擎
- **#5 Chat answers shallow** — grounded-answer-generation pipeline
- **#6 archive_url not using ArchiveBox** — CLI 对接 ArchiveBox

### 清理

- 删除 `analyze_hypothesis()` 旧规则引擎（已被 `analyze_hypothesis_llm()` 替代）
- 删除 `_stage_hypothesis_sync()` 同步降级路径（不降级原则）
- 测试改为直接构造 `ACHResult`，不再依赖旧规则引擎
