<!-- Author: msq -->

## ADDED Requirements

### Requirement: Conversational answers MUST include evidence citations
每次对话回答 MUST 返回证据引用与 trace_id。

#### Scenario: FACT answer without citations is blocked
- **WHEN** 对话回答被标记为 FACT 但 citations 为空
- **THEN** 系统拒绝该响应并降级为 HYPOTHESIS 或 cannot_answer

### Requirement: System MUST return structured cannot-answer response
证据不足时 MUST 返回结构化不可回答结果，而非编造结论。

#### Scenario: Evidence is insufficient
- **WHEN** QueryPlan 执行后无足够证据
- **THEN** 返回 `cannot_answer_reason` 和可继续检索建议

### Requirement: Chat trace MUST be replayable
每次对话调用 MUST 可回放 QueryPlan 与引用链。

#### Scenario: Trace replay request
- **WHEN** 请求 `GET /analysis/chat/{trace_id}`
- **THEN** 返回对应查询计划、检索步骤、引用证据
