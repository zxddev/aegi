<!-- Author: msq -->

## Decisions

1. 回答分级：FACT/INFERENCE/HYPOTHESIS。
2. 无证据结论禁止输出 FACT。
3. 输出必须携带引用链与不可回答原因。

## Input / Output Contracts

- 输入：`question`、`case_uid`、`time_range(optional)`、`language(optional)`
- 中间产物：`QueryPlanV1`（filters、joins、retrieval_steps、risk_flags）
- 输出：`AnswerV1`
  - 必填：`answer_text`、`answer_type`、`evidence_citations[]`、`trace_id`
  - 可选：`cannot_answer_reason`、`follow_up_questions[]`

## API Contract

- `POST /cases/{case_uid}/analysis/chat`
  - request: `question`, optional context filters
  - response: `AnswerV1`
- `GET /cases/{case_uid}/analysis/chat/{trace_id}`
  - response: QueryPlan + retrieval trace + citations

## Retrieval Strategy (Staged)

### P1 (No New Infra Dependency)

1. 使用 Postgres FTS + JSONB 过滤作为默认检索路径。
2. 复用现有 SourceClaim/Assertion 索引与结构化过滤。
3. 禁止在 P1 自行引入 Qdrant/pgvector 新依赖。

### P2 (Optional Upgrade)

1. 在依赖评审通过后，升级为 pgvector 或 Qdrant 语义检索。
2. 语义检索仅作为召回增强，不替代证据链引用校验。

## Hallucination Gate

1. 无有效引用时，`answer_type` 不得为 FACT。
2. 引用失效或不可定位时，输出 `cannot_answer_reason`。
3. 所有对话响应必须可通过 trace 回放。

## Fixtures

- `defgeo-chat-001`：可回答问题（有充分证据）
- `defgeo-chat-002`：不可回答问题（证据不足）

## Acceptance

1. 对话响应 100% 携带 trace_id。
2. FACT 响应 100% 携带可定位 evidence citations。
3. 不可回答场景返回结构化原因，不输出编造结论。
