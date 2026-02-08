<!-- Author: msq -->

# Changelog

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
