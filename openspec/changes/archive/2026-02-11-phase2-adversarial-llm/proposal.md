# Proposal: hypothesis_adversarial LLM 三角色辩论

## Why
规则版 defense/prosecution/judge 只做简单 UID 分类，缺乏真正论证能力。

## What
- 新增 `async aevaluate_adversarial(llm=)`
- 3 次 LLM 调用，structured JSON output
- 无 LLM 时 fallback 到规则版本
