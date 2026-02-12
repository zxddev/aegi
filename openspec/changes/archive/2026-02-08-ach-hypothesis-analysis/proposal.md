<!-- Author: msq -->

## Why

ACH 自动化是中期核心能力，需要独立 contracts 与评测标准。

## What Changes

- 新增 Hypothesis 模型、支持/反驳关系与证据缺口输出。
- 引入对抗式评估流程（Defense/Prosecution/Judge）提升推理稳健性。

## Capabilities

### New Capabilities

- `ach-hypothesis-analysis`

## Dependencies

- Hard dependency: `foundation-common-contracts`
- Upstream dependency: `automated-claim-extraction-fusion`
- Optional enrichment: `multilingual-evidence-chain`

## Impact

- `code/aegi-core/src/aegi_core/db/models/hypothesis.py`
- `code/aegi-core/src/aegi_core/services/hypothesis_engine.py`
- `code/aegi-core/src/aegi_core/services/hypothesis_adversarial.py`
- `code/aegi-core/src/aegi_core/api/routes/hypotheses.py`
- `code/aegi-core/tests/test_ach_hypothesis_engine.py`
