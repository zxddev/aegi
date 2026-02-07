<!-- Author: msq -->

## 1. Schema + LLM ACH 分析函数

- [x] 1.1 在 `hypothesis_engine.py` 新增 `AssertionJudgment` / `ACHAnalysisResult` schema
- [x] 1.2 新增 `analyze_hypothesis_llm()` — LLM structured output ACH 分析
- [x] 1.3 从 judgments 计算 supporting/contradicting/gap/coverage/confidence

## 2. Pipeline orchestrator 改造

- [x] 2.1 `_hypothesis_with_llm` 改用 `analyze_hypothesis_llm`
- [x] 2.2 删除 `_stage_hypothesis_sync`
- [x] 2.3 `run_full` sync 路径 hypothesis 阶段改为 skip
- [x] 2.4 `run_full_async` 无 LLM 时 hypothesis 阶段 hard error

## 3. API route 改造

- [x] 3.1 `score_hypothesis` 注入 LLM 依赖，调用 `analyze_hypothesis_llm`
- [x] 3.2 `generate_hypotheses` 内部 ACH 改用 LLM

## 4. 清理

- [x] 4.1 旧 `analyze_hypothesis` 标记 deprecated
- [x] 4.2 ruff lint + format 通过
