# Proposal: scenario_generator LLM 情景推演

## Why
规则版只能基于 hypothesis 一对一生成 forecast，缺乏综合推演能力。

## What
- 新增 `async agenerate_forecasts(llm=)`
- LLM 生成 best/worst/most_likely 三分支情景
