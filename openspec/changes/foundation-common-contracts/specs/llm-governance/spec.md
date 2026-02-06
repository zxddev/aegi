<!-- Author: msq -->

## ADDED Requirements

### Requirement: LLM calls MUST be governed by versioned policy
所有 LLM 调用 MUST 携带 `model_id`、`prompt_version`、`budget_context`，并写入审计链。

#### Scenario: LLM invocation is auditable
- **WHEN** 任一功能调用 LLM
- **THEN** 记录模型、提示词版本、token/cost、trace_id

### Requirement: Ungrounded outputs MUST NOT be emitted as FACT
若输出无可验证证据引用，系统 MUST 降级为 HYPOTHESIS/INFERENCE，不得标记 FACT。

#### Scenario: Missing citation forces downgrade
- **WHEN** LLM 输出没有有效 evidence citation
- **THEN** 输出等级降级并附带原因

### Requirement: Budget and failure paths MUST be deterministic
超预算或模型不可用时 MUST 返回结构化降级结果，不得 silent fail。

#### Scenario: Model unavailable triggers fallback
- **WHEN** 上游模型超时或不可用
- **THEN** 执行预定义 fallback，并记录降级原因
