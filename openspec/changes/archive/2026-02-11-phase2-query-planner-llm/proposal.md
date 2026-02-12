# Proposal: query_planner LLM 查询规划

## Why
规则版只生成固定的 source_claims + assertions 两步检索，无法理解问题意图。

## What
- 新增 `async aplan_query(llm=)`
- LLM 分析意图 → 生成 retrieval_steps + risk_flags
