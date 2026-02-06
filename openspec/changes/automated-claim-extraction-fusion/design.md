<!-- Author: msq -->

## Decisions

1. 抽取器先保真（quote/selectors）后归一。
2. 融合必须输出 rationale 与冲突原因。

## Input / Output Contracts

- 输入（Extract）：`artifact_version_uid`、`chunk_uid`、`chunk.text`、`anchor_set`
- 输出（Extract）：`SourceClaimV1[]`
  - 必填：`quote`、`selectors`、`evidence_uid`、`chunk_uid`、`artifact_version_uid`
- 输入（Fuse）：`SourceClaimV1[]`
- 输出（Fuse）：`AssertionV1[]`
  - 必填：`kind`、`value`、`source_claim_uids`、`confidence`、`rationale`

## API Contract

- `POST /cases/{case_uid}/pipelines/claim_extract`
  - request: `artifact_version_uid` 或 `chunk_uids`
  - response: `source_claim_uids[] + trace_id`
- `POST /cases/{case_uid}/pipelines/assertion_fuse`
  - request: `source_claim_uids[]`
  - response: `assertion_uids[] + conflict_set + trace_id`

## Conflict Definition

冲突最小定义（P1）：

1. 同一事件窗口内，关键值字段互斥（例如同一主体同一时间不同地点）
2. modality 冲突（confirmed vs denied）

冲突必须保留，不允许静默覆盖。

## Fixtures

- 基础集：`defgeo-claim-001`（单语）
- 冲突集：`defgeo-claim-002`（同事件冲突叙述）

## LLM Strategy

1. 抽取阶段可用 LLM，但必须附 `prompt_version`。
2. 融合阶段优先规则，LLM 仅用于歧义解释。
3. 无 selectors 的 LLM 输出直接拒收。

## Acceptance

1. `claim_grounding_rate >= 0.97`
2. 冲突样例可稳定复现 conflict_set
3. pipeline 输出全部带 trace_id
