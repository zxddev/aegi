<!-- Author: msq -->

## Why

对话式分析是分析师主入口，需要独立定义输入输出合同与不可回答策略。

## What Changes

- 新增 NL 查询到结构化查询计划。
- 回答强制附证据链与 trace_id。
- 增加不可回答/证据不足的标准化返回。

## Capabilities

### New Capabilities

- `conversational-analysis-evidence-qa`

## Dependencies

- Hard dependency: `foundation-common-contracts`
- Upstream dependency: `automated-claim-extraction-fusion`
- Optional enrichment: `multilingual-evidence-chain`

## Impact

- `code/aegi-core/src/aegi_core/api/routes/query.py`
- `code/aegi-core/src/aegi_core/services/query_planner.py`
- `code/aegi-core/src/aegi_core/services/answer_renderer.py`
- `code/aegi-core/tests/test_conversational_query_api.py`
- `code/aegi-core/tests/test_conversational_hallucination_gate.py`
