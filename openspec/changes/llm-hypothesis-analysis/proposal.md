<!-- Author: msq -->

## Why

`hypothesis_engine.analyze_hypothesis()` 是纯关键词匹配规则引擎：
- 用 hypothesis text 拆词（>3字符）与 assertion value 做词汇重叠判断"相关性"
- 用硬编码关键词集 `{"denied","rejected",...}` vs `{"confirmed","affirmed",...}` 分类支持/反证
- 真实情报文本几乎不命中这些关键词 → coverage ≈ 0, confidence ≈ 0, gap_list ≈ 全部

orchestrator 两条路径都经过此破引擎：
- `_hypothesis_with_llm`: LLM 生成假设文本，但 ACH 分析仍走规则 → 稀疏
- `_stage_hypothesis_sync`: 硬编码 "Auto-generated hypothesis" → 更稀疏
- API `score_hypothesis`: 直接调规则引擎 → 同样稀疏

与 #1 KG build 同模式问题：规则引擎无法处理真实文本，需 LLM structured output 替代。

## What Changes

- `hypothesis_engine.py` 新增 `analyze_hypothesis_llm()` — LLM 对每个 assertion 判断
  support/contradict/irrelevant 并给出理由
- `pipeline_orchestrator.py` 的 `_hypothesis_with_llm` 改用 LLM ACH 分析
- `_stage_hypothesis_sync` 删除（无 LLM = hard error，不降级）
- API route `score_hypothesis` 注入 LLM 依赖，调用 LLM 分析

## Capabilities

### Modified Capabilities

- `ach-hypothesis-analysis`：ACH 分析从关键词匹配升级为 LLM structured output

## Dependencies

- Hard dependency: `LLMClient`（已有 infra，litellm 8713）
