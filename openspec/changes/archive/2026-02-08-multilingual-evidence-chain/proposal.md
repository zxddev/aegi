<!-- Author: msq -->

## Why

多语言语义理解与跨语言实体对齐是 P1 核心差异化能力，需要独立 change 便于并行推进。

## What Changes

- 增加 SourceClaim 多语言字段与翻译保真链路。
- 实现跨语言实体对齐与可审计映射。
- 增加跨语言 fixtures 与对齐评测指标。

## Capabilities

### New Capabilities

- `multilingual-evidence-chain`

## Dependencies

- Hard dependency: `foundation-common-contracts`
- Soft dependency: `automated-claim-extraction-fusion`（复用 SourceClaim 输出）

## Impact

- `code/aegi-core/src/aegi_core/contracts/schemas.py`（复用 foundation 预置字段，不在本 change 新增 schema）
- `code/aegi-core/src/aegi_core/services/multilingual_pipeline.py`
- `code/aegi-core/src/aegi_core/services/entity_alignment.py`
- `code/aegi-core/tests/test_multilingual_pipeline.py`
- `code/aegi-core/tests/test_cross_lingual_entity_alignment.py`
