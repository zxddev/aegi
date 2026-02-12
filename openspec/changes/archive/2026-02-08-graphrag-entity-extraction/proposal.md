<!-- Author: msq -->

## Why

kg_mapper.build_graph() 当前是纯规则引擎，实体提取完全依赖 assertion.value["attributed_to"]
这个可选字段。当 SourceClaim 没有 attributed_to 时（常见情况），KG 构建产出 entities:0,
events:0, relations:0——图谱能力形同虚设。

baize-core（ADR-001 P1 主参考）已有完整 GraphRAG pipeline：LLM structured output 抽取
实体/事件/关系，写入 Neo4j。aegi 应移植此能力而非自造简化版。

## What Changes

- 移植 baize-core 的 ExtractionResult schema 到 aegi_core.contracts.extraction
- 新建 graphrag_pipeline.py，用 LLM structured output 从文本抽取实体/事件/关系
- kg_mapper.build_graph() 替换为 GraphRAG pipeline 调用（async，需 LLM）
- pipeline_orchestrator kg_build 阶段调用 GraphRAG pipeline

## Capabilities

### New Capabilities

- `graphrag-entity-extraction`：LLM 结构化抽取实体、事件、关系三元组

### Modified Capabilities

- `knowledge-graph-ontology-evolution`：kg_build 从规则引擎升级为 GraphRAG

## Dependencies

- Hard dependency: `LLMClient`（已有 infra，litellm 8713）
- Hard dependency: `Neo4jStore`（已有 infra，neo4j 8714/8715）
- Design reference: `开源项目参考/baize-core/src/baize_core/graph/graphrag_pipeline.py`
- Design reference: `开源项目参考/baize-core/src/baize_core/schemas/extraction.py`

## Non-Goals

- 不含 community detection（Louvain/Leiden），后续独立 openspec
- 不改 assertion_fuser（本次只改 KG 构建）
- 不加新 API 端点（复用现有 build_from_assertions）

## Impact

- `code/aegi-core/src/aegi_core/contracts/extraction.py`（新建）
- `code/aegi-core/src/aegi_core/services/graphrag_pipeline.py`（新建）
- `code/aegi-core/src/aegi_core/services/kg_mapper.py`（重写）
- `code/aegi-core/src/aegi_core/services/pipeline_orchestrator.py`（kg_build 阶段）
- `code/aegi-core/src/aegi_core/api/routes/kg.py`（传 LLM 依赖）
