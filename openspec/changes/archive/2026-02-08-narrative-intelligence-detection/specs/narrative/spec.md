<!-- Author: msq -->

## ADDED Requirements

### Requirement: Narrative chain MUST be replayable
每条叙事传播链 MUST 支持回放并可追溯源节点。

#### Scenario: Narrative trace returns source chain
- **WHEN** 查询 narrative trace
- **THEN** 返回时间序列传播节点与 source_claim_uids

### Requirement: Coordination detection MUST include false-positive explanation
协同行为检测结果 MUST 附带误报解释字段。

#### Scenario: Coordination signal reports uncertainty
- **WHEN** 模型置信度低于阈值
- **THEN** 标记为 low_confidence 并说明原因

### Requirement: Conflicting narratives MUST coexist
冲突叙事 MUST 并存展示，不得强制合并。

#### Scenario: Opposite narratives remain visible
- **WHEN** 同一事件存在相反叙事
- **THEN** 系统保留两条叙事及各自证据链
