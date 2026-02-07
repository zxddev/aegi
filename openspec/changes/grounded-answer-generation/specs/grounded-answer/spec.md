<!-- Author: msq -->

## MODIFIED Requirements

### Requirement: 证据格式化

chat 回答前，将检索到的 SourceClaim 格式化为编号证据上下文字符串。

#### Scenario: 多条证据格式化

- **WHEN** 检索到 N 条 SourceClaim（N >= 1）
- **THEN** 生成格式 `[1] quote_text\n[2] quote_text\n...` 的证据上下文
- **AND** 返回 index → EvidenceCitation 的映射

#### Scenario: 零证据

- **WHEN** 检索到 0 条 SourceClaim
- **THEN** 不调用 LLM，直接走 cannot_answer 路径

### Requirement: LLM Grounded 回答生成

用 LLM 基于编号证据生成带内联引用的回答。

#### Scenario: 正常生成

- **WHEN** 有格式化证据上下文 + 用户问题
- **THEN** 调用 LLM 生成回答，要求内联 [N] 引用
- **AND** 从回答文本中提取实际引用的编号，映射回 EvidenceCitation

#### Scenario: LLM 调用失败

- **WHEN** LLM 调用抛异常
- **THEN** 返回 cannot_answer_reason = "llm_unavailable"
- **AND** 不降级为模板字符串

### Requirement: Hallucination gate 保留

现有 hallucination gate 逻辑不变。

#### Scenario: 无引用降级

- **WHEN** LLM 生成的回答未引用任何证据编号
- **THEN** answer_type 降级为 HYPOTHESIS
