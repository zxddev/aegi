<!-- Author: msq -->

## Why

知识图谱与本体演化是长期可扩展性的核心，需单独定义兼容策略。

## What Changes

- 实现 Entity/Event/Relation 持久层与本体版本演化机制。
- 将 Assertion 输出映射为图谱节点/边，形成可回放图更新流程。

## Capabilities

### New Capabilities

- `knowledge-graph-ontology-evolution`

## Dependencies

- Hard dependency: `foundation-common-contracts`
- Hard dependency: `automated-claim-extraction-fusion`（依赖 Assertion schema 稳定）

## Impact

- `code/aegi-core/src/aegi_core/db/models/entity.py`
- `code/aegi-core/src/aegi_core/db/models/event.py`
- `code/aegi-core/src/aegi_core/db/models/relation.py`
- `code/aegi-core/src/aegi_core/services/kg_mapper.py`
- `code/aegi-core/src/aegi_core/services/ontology_versioning.py`
- `code/aegi-core/tests/test_kg_mapping_and_ontology_versioning.py`
