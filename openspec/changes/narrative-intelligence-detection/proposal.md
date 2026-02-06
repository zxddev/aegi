<!-- Author: msq -->

## Why

叙事识别与传播检测是 P2 关键能力，应独立建模避免与 ACH 混杂。

## What Changes

- 新增 Narrative 实体、传播路径、协同行为检测。
- 增加叙事溯源、冲突叙事并存展示与回放接口。

## Capabilities

### New Capabilities

- `narrative-intelligence-detection`

## Dependencies

- Hard dependency: `foundation-common-contracts`
- Upstream dependency: `automated-claim-extraction-fusion`
- Optional enrichment: `multilingual-evidence-chain`

## Impact

- `code/aegi-core/src/aegi_core/db/models/narrative.py`
- `code/aegi-core/src/aegi_core/services/narrative_builder.py`
- `code/aegi-core/src/aegi_core/services/coordination_detector.py`
- `code/aegi-core/src/aegi_core/api/routes/narratives.py`
- `code/aegi-core/tests/test_narrative_detection.py`
