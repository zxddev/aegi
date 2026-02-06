<!-- Author: msq -->

## Why

元认知能力（偏见/盲区/可信度）决定分析结果是否可被信任，需要独立评测与解释层。

## What Changes

- 新增偏见检测、盲区识别、可信度分解评分。
- 为每个 Judgment 输出可解释质量报告，并回溯上游能力来源。

## Capabilities

### New Capabilities

- `meta-cognition-quality-scoring`

## Dependencies

- Hard dependency: `foundation-common-contracts`
- Hard dependency: `automated-claim-extraction-fusion`
- Hard dependency: `ach-hypothesis-analysis`
- Hard dependency: `narrative-intelligence-detection`
- Hard dependency: `knowledge-graph-ontology-evolution`
- Hard dependency: `predictive-causal-scenarios`

## Impact

- `code/aegi-core/src/aegi_core/services/confidence_scorer.py`
- `code/aegi-core/src/aegi_core/services/bias_detector.py`
- `code/aegi-core/src/aegi_core/services/blindspot_detector.py`
- `code/aegi-core/src/aegi_core/api/routes/quality.py`
- `code/aegi-core/tests/test_meta_cognition_quality.py`
