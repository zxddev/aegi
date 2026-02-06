<!-- Author: msq -->

## ADDED Requirements

### Requirement: Judgment confidence MUST be decomposable and auditable
每个 Judgment 的可信度 MUST 可拆解、可审计、可复核。

#### Scenario: Confidence score includes breakdown
- **WHEN** 请求质量评分
- **THEN** 返回 `confidence_breakdown`（来源、覆盖、一致性、时效）

### Requirement: Bias and blindspot detection MUST be evidence-linked
偏见与盲区提示 MUST 指向具体证据链，而非抽象告警。

#### Scenario: Bias flag references source claims
- **WHEN** 触发偏见告警
- **THEN** 输出关联的 source_claim_uids 与判断依据

### Requirement: Missing upstream outputs MUST block final quality score
上游关键模块输出缺失时 MUST 返回 pending_inputs，禁止产出伪完整评分。

#### Scenario: Upstream dependency not ready
- **WHEN** 预测或叙事模块结果缺失
- **THEN** 质量评分接口返回 pending_inputs 状态
