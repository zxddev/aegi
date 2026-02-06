<!-- Author: msq -->

## ADDED Requirements

### Requirement: Translated claims MUST retain original anchors
翻译后的 claim MUST 可回溯到原文 SourceClaim 与 selectors。

#### Scenario: Translation keeps provenance
- **WHEN** 系统生成翻译文本
- **THEN** 保留 original_quote、selectors、artifact_version_uid

### Requirement: Cross-lingual entity alignment MUST be evidence-linked
跨语言实体对齐输出 MUST 带 source_claim_uid 与置信度。

#### Scenario: Aligned entity has evidence pointer
- **WHEN** 系统判定多语言别名为同一实体
- **THEN** 输出包含 canonical_id、alias、source_claim_uid、confidence

### Requirement: Uncertain alignment MUST be explicitly marked
低置信对齐结果 MUST 标记为 uncertain，禁止静默合并。

#### Scenario: Ambiguous alias is not auto-merged
- **WHEN** alias 匹配存在多候选且置信度不足
- **THEN** 结果标记 uncertain 并进入复核队列
