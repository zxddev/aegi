# Spec

- chat.py: `plan_query()` → `await aplan_query(llm=llm)`
- narratives.py: build 用 `abuild_narratives_with_uids(embed_fn=llm.embed)`，detect 传 `embeddings`
- forecast.py: 注入 LLMClient，`svc_generate` → `await svc_agenerate(llm=llm)`
- hypotheses.py: score 后调 `aevaluate_adversarial(llm=)`，结果写入 `adversarial_result`
- orchestrator: STAGE_ORDER += adversarial_evaluate，async 路径升级
