<!-- Author: msq -->

## ADDED Requirements

### Requirement: Hypothesis output MUST include supporting and contradicting evidence
每个假设 MUST 输出支持证据、反证与缺口说明。

#### Scenario: Incomplete hypothesis output is rejected
- **WHEN** 假设输出缺少 support/contradict/gap 任一项
- **THEN** 标记为无效结果并拒绝发布

### Requirement: ACH reasoning MUST be replayable through evidence chain
Hypothesis 解释 MUST 可回放到 Assertion 与 SourceClaim。

#### Scenario: Explain endpoint returns provenance links
- **WHEN** 调用 hypothesis explain
- **THEN** 返回 assertion_uid/source_claim_uid 列表与理由

### Requirement: Adversarial triad results MUST preserve disagreement
Defense/Prosecution/Judge 的分歧 MUST 被保留，不得被单结果覆盖。

#### Scenario: Competing judgments coexist
- **WHEN** defense 与 prosecution 结论冲突
- **THEN** judge 输出必须包含冲突摘要与裁决依据
