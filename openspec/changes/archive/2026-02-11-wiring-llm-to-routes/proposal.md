# Proposal: Phase 1+2 分析能力接入 API 路由和 orchestrator

## Why
Phase 1（7 个规则改进）和 Phase 2（4 个 LLM async 方法）已实现并通过测试，
但 API 路由和 pipeline orchestrator 仍调用旧的 sync 版本，LLM 能力完全未上线。

## What
6 个文件改动，将所有分析能力接通到实际请求路径：
- chat.py → aplan_query(llm=)
- narratives.py → abuild_narratives_with_uids(embed_fn=) + embeddings
- forecast.py → agenerate_forecasts(llm=)
- hypotheses.py → aevaluate_adversarial(llm=)
- pipeline_orchestrator.py → 新增 adversarial_evaluate 阶段 + async 升级
