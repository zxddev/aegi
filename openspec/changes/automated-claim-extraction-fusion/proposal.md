<!-- Author: msq -->

## Why

自动化 claim 抽取与融合是所有上层分析能力的基础，需要独立提效与质量控制。

该 change 是 P1 基础层，直接决定 ACH/叙事/KG 的输入稳定性。

## What Changes

- 抽取器从 chunk 产出结构化 SourceClaim。
- 融合器生成 Assertion 并保留冲突。
- 固化 claim/extract 与 assertion/fuse 的 API 合同、fixtures、回归指标。
- 所有输出复用 foundation 的共享 schema 与 LLM 治理合同。

## Capabilities

### New Capabilities

- `automated-claim-extraction-fusion`

## Dependencies

- Hard dependency: `foundation-common-contracts`
- Contract dependency: `contracts/schemas.py`、`contracts/llm_governance.py`

## Impact

- `code/aegi-core/src/aegi_core/services/claim_extractor.py`
- `code/aegi-core/src/aegi_core/services/assertion_fuser.py`
- `code/aegi-core/src/aegi_core/api/routes/cases.py`（新增 pipeline 入口或调用路径）
- `code/aegi-core/tests/test_claim_extraction_pipeline.py`
- `code/aegi-core/tests/test_assertion_fusion_pipeline.py`
