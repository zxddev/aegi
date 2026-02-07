<!-- Author: msq -->

## Scenario 1: LLM ACH 分析正确分类 assertions

Given 一个假设 "Country Alpha is preparing a military exercise"
And 3 个 assertions：一个 confirmed 部署，一个 denied 参与，一个无关天气
When 调用 `analyze_hypothesis_llm()`
Then 部署 assertion 被标记 support
And denied assertion 被标记 contradict
And 天气 assertion 被标记 irrelevant
And coverage_score > 0, confidence > 0

## Scenario 2: Pipeline async 路径使用 LLM ACH

Given orchestrator 有 LLM client
And 有 assertions 和 source_claims
When 调用 `run_full_async(stages=["hypothesis_analyze"])`
Then hypothesis_analyze 阶段 status = "success"
And 产出的 hypotheses 有非零 confidence 和 supporting_assertion_uids

## Scenario 3: 无 LLM 时 hard error

Given orchestrator 没有 LLM client
When 调用 `run_full_async(stages=["hypothesis_analyze"])`
Then hypothesis_analyze 阶段 status = "error"
And 不产出任何 hypothesis（不降级到规则引擎）

---

## Acceptance Criteria

1. `analyze_hypothesis_llm()` 返回 ACHResult，judgments 来自 LLM structured output
2. coverage_score 和 confidence 从 LLM judgments 计算，不再依赖关键词匹配
3. `_stage_hypothesis_sync` 删除，sync `run_full` 的 hypothesis 阶段 skip
4. API `score_hypothesis` 使用 LLM 分析
5. 无 LLM 时 hypothesis 阶段 hard error，不 fallback
