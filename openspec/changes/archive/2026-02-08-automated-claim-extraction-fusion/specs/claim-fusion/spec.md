<!-- Author: msq -->

## ADDED Requirements

### Requirement: Assertions MUST be derived from SourceClaims
任何 Assertion MUST 至少关联一条 SourceClaim。

#### Scenario: Assertion without source claims is rejected
- **WHEN** 创建 Assertion 的输入 `source_claim_uids` 为空
- **THEN** 返回结构化错误并拒绝写入

### Requirement: Claim extraction MUST preserve quote selectors
SourceClaim 抽取输出 MUST 包含可定位原文的 selectors。

#### Scenario: Missing selectors fails extraction
- **WHEN** 抽取结果缺失 selectors
- **THEN** 输出标记为 invalid，不进入融合阶段

### Requirement: Conflict set MUST be explicit and replayable
融合阶段发现冲突时 MUST 输出 conflict_set，并可通过 trace_id 回放。

#### Scenario: Contradicting claims produce conflict_set
- **WHEN** 两条 claims 在同事件窗口内互斥
- **THEN** 输出包含冲突类型、涉及 claim_uid、rationale
