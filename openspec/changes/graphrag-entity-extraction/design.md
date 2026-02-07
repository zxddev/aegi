<!-- Author: msq -->

## Context

baize-core 的 GraphRAG pipeline 已验证：LLM structured output → ExtractionResult
（entities + events + relations）→ Neo4j upsert。aegi 需适配移植，保留国防/地缘
情报领域的 9 种实体类型、12 种事件类型、10 种关系类型。

## Goals / Non-Goals

**Goals:**
- LLM 从 SourceClaim quote 文本中抽取结构化实体/事件/关系
- 抽取结果写入 Neo4j（Entity/Event 节点 + 关系边）
- 保留 assertion→entity 溯源链（source_assertion_uids）
- LLM 不可用 = 硬错误（不降级为规则引擎）

**Non-Goals:**
- Community detection（后续独立 openspec）
- 增量关系抽取（extract_relations_only，后续）
- 地理坐标解析（GeoPoint，后续）

## Decisions

### Decision 1: ExtractionResult schema

从 baize-core/schemas/extraction.py 适配，保留核心字段，去掉 aegi 暂不需要的
（GeoPoint、TimeRange 简化为 str）。用 Pydantic BaseModel 做 LLM structured output。

### Decision 2: GraphRagPipeline 服务

```
class GraphRagPipeline:
    llm: LLMClient
    neo4j: Neo4jStore

    async def extract_and_index(
        assertions: list[AssertionV1],
        case_uid: str,
        ontology_version: str,
    ) -> BuildGraphResult
```

对每个 assertion 的 source_claim quotes 调用 LLM structured output，
合并去重后写入 Neo4j。

### Decision 3: LLM prompt

参考 baize-core 的 EXTRACTION_SYSTEM_PROMPT，面向国防/地缘情报领域：
- 实体：国家、组织、部队、设施、装备、地点、人物
- 事件：军事行动、外交活动、部署变化、演习、冲突
- 关系：隶属、位置、同盟、敌对、合作、参与、因果、时序

输出必须符合 ExtractionResult JSON Schema。

### Decision 4: 名称去重

entity_name_to_uid 映射 + 模糊匹配（参考 baize-core _fuzzy_match_entity），
避免同一实体重复创建节点。

### Decision 5: kg_mapper 保留为 fallback-free

旧的规则引擎 build_graph() 删除。LLM 不可用时直接报错，不降级。
