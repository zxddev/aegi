# Proposal: causal_reasoner 反事实推理 + 混淆因素

## Why
因果链只有 strength 和 temporal_consistent，缺少反事实评估和混淆因素。

## What
- CausalLink 新增 `counterfactual_score` 和 `confounders`
- 新增 `async aanalyze_causal_links(llm=)`
