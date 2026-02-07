<!-- Author: msq -->

## 1. extraction schema

- [ ] 1.1 新建 `aegi_core/contracts/extraction.py`，从 baize-core 适配
      ExtractionResult / ExtractedEntity / ExtractedEvent / ExtractedRelation
      及对应 Enum 类型（EntityType 9 种、EventType 12 种、RelationType 10 种）

## 2. graphrag_pipeline.py

- [ ] 2.1 新建 `aegi_core/services/graphrag_pipeline.py`
- [ ] 2.2 实现 `GraphRagPipeline.extract_and_index()`：
      - 收集 assertions 的 quote 文本
      - 调用 LLM structured output → ExtractionResult
      - entity_name_to_uid 去重 + fuzzy match
      - 转换为 EntityV1 / EventV1 / RelationV1
      - 写入 Neo4j（upsert_nodes + upsert_edges）
      - 返回 BuildGraphResult

## 3. kg_mapper.py 重写

- [ ] 3.1 删除旧的规则引擎 build_graph()
- [ ] 3.2 新 build_graph() 为 async，内部调用 GraphRagPipeline

## 4. pipeline_orchestrator.py

- [ ] 4.1 `_kg_build_and_write()` 改用新的 async build_graph()

## 5. kg.py route

- [ ] 5.1 `build_from_assertions` 端点注入 LLM 依赖，调用 async build_graph()

## 6. 验收

- [ ] 6.1 ruff lint + format 通过
- [ ] 6.2 现有测试全部通过
- [ ] 6.3 手动验证：调用 build_from_assertions 后 Neo4j 有实体/事件/关系节点
