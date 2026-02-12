<!-- Author: msq -->

## ADDED Requirements

### Requirement: LLM ACH analysis MUST correctly classify assertions
LLM ACH 分析 MUST 正确分类 assertions 为 support/contradict/irrelevant。

#### Scenario: LLM ACH 分析正确分类 assertions

Given 一个假设 "Country Alpha is preparing a military exercise"
And 3 个 assertions：一个 confirmed 部署，一个 denied 参与，一个无关天气
When 调用 `analyze_hypothesis_llm()`
Then 部署 assertion 被标记 support
And denied assertion 被标记 contradict
And 天气 assertion 被标记 irrelevant
And coverage_score > 0, confidence > 0

### Requirement: Pipeline async path MUST use LLM ACH
Pipeline async 路径 MUST 使用 LLM ACH 进行假设分析。

#### Scenario: Pipeline async 路径使用 LLM ACH

Given orchestrator 有 LLM client
And 有 assertions 和 source_claims
When 调用 `run_full_async(stages=["hypothesis_analyze"])`
Then hypothesis_analyze 阶段 status = "success"
And 产出的 hypotheses 有非零 confidence 和 supporting_assertion_uids

### Requirement: System MUST hard error when LLM unavailable
无 LLM 时系统 MUST 产生 hard error，不降级到规则引擎。

#### Scenario: 无 LLM 时 hard error

Given orchestrator 没有 LLM client
When 调用 `run_full_async(stages=["hypothesis_analyze"])`
Then hypothesis_analyze 阶段 status = "error"
And 不产出任何 hypothesis（不降级到规则引擎）
