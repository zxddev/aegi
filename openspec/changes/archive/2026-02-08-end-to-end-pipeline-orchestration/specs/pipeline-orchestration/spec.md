<!-- Author: msq -->

## ADDED Requirements

### Requirement: Pipeline orchestrator MUST support full and incremental execution
编排器 MUST 支持全链路执行和从任意阶段开始的增量执行。

#### Scenario: Full analysis from claims
- **WHEN** 调用 full_analysis 且有 source_claims
- **THEN** 按 STAGE_ORDER 依次执行所有阶段，返回 PipelineResult

#### Scenario: Start from hypothesis stage
- **WHEN** 调用 run_stage 指定从 hypothesis_analyze 开始
- **THEN** 跳过前置阶段，直接执行 hypothesis_analyze

### Requirement: Missing inputs MUST cause skip not crash
缺失输入时阶段 MUST 标记为 skipped，不得抛出异常终止整个 pipeline。

#### Scenario: Empty claims skips all stages
- **WHEN** source_claims 为空
- **THEN** 所有阶段 status = "skipped"，pipeline 正常返回
