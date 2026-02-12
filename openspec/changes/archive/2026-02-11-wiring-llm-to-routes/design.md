# Design

每个路由注入 LLMClient（via get_llm_client），调用对应 async 方法传入 llm=。
所有 async 方法内部已有 fallback：llm=None 时走规则版本。
orchestrator STAGE_ORDER 新增 adversarial_evaluate，run_full_async 升级 narrative/forecast 为 async+LLM。
sync run_full 不动（向后兼容）。
