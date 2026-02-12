# Fix: AdversarialEvaluateStage 签名不匹配

## 问题

`builtin.py` 中 `AdversarialEvaluateStage.run()` 直接将 `ctx.hypotheses`（`list[HypothesisV1]`）传给 `aevaluate_adversarial()`，但该函数的第一个参数期望的是单个 `ACHResult`。

类型不匹配会导致运行时 `AttributeError`（`HypothesisV1` 没有 `hypothesis_text` 等 `ACHResult` 字段）。

## 修复

参照 `PipelineOrchestrator._run_adversarial_llm()` 中的正确调用方式：

1. 遍历 `ctx.hypotheses`
2. 为每个 `HypothesisV1` 构造对应的 `ACHResult`（`label → hypothesis_text`, `supporting_assertion_uids`, `confidence`）
3. 逐个调用 `aevaluate_adversarial()`，收集结果列表

## 修改文件

- `src/aegi_core/services/stages/builtin.py` — `AdversarialEvaluateStage.run()`

## 测试

```
uv run pytest tests/test_ach_hypothesis_engine.py tests/test_pipeline_orchestration.py -x -v
# 19 passed
```
