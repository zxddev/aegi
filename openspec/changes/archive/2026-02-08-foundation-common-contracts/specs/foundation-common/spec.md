<!-- Author: msq -->

## ADDED Requirements

### Requirement: All feature changes MUST depend on shared contracts
后续功能 change 在实现前 MUST 复用并通过公共合同测试。

#### Scenario: Feature change runs contract suite
- **WHEN** 任一功能 change 提交实现
- **THEN** 公共 contract tests 全部通过

### Requirement: Shared contract outputs MUST be file-addressable
foundation MUST 产出可直接引用的共享合同文件，后续 change 不得重复定义同名核心 schema。

#### Scenario: Feature change imports shared schemas
- **WHEN** 功能 change 实现 SourceClaim/Assertion/Hypothesis/Narrative 逻辑
- **THEN** 其输入输出 schema 来自 `contracts/schemas.py`

### Requirement: Foundation MUST reserve multimodal compatibility fields
共享合同 MUST 预留 `modality` 与媒体片段定位字段，避免后续多模态改坏核心模型。

#### Scenario: Text-first feature keeps multimodal compatibility
- **WHEN** 当前只实现文本能力
- **THEN** schema 仍可表达 image/video/audio 的占位字段
