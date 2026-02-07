<!-- Author: msq -->

## Scenario: GraphRAG 从情报文本抽取实体/事件/关系

**Given** 一组 AssertionV1，其 source_claim 包含情报文本 quote
**When** 调用 POST /cases/{case_uid}/kg/build_from_assertions
**Then** LLM 从 quote 文本中抽取实体（国家/组织/部队/设施等）、事件（军事行动/外交等）、关系（隶属/同盟/敌对等）
**And** 抽取结果写入 Neo4j（Entity/Event 节点 + 关系边）
**And** 返回 entities > 0, events >= 0, relations >= 0

## Scenario: LLM 不可用时硬错误

**Given** LLM 服务不可达
**When** 调用 build_from_assertions
**Then** 返回错误，不降级为规则引擎，不返回空图谱假装成功

## Scenario: 实体去重

**Given** 多个 assertion 提到同一实体（如 "Russia" 和 "Russian Federation"）
**When** GraphRAG pipeline 处理
**Then** 通过 name_to_uid 映射 + fuzzy match 合并为同一节点
**And** Neo4j 中不产生重复 Entity 节点

## Acceptance Criteria

1. build_from_assertions 返回 entities > 0（给定非空情报文本）
2. Neo4j 中可查到对应 Entity/Event 节点和关系边
3. 每个 Entity/Event 保留 source_assertion_uids 溯源
4. LLM 不可用 = 硬错误（status != "ok"）
5. 抽取使用国防/地缘情报领域的类型体系（9 实体 + 12 事件 + 10 关系）
