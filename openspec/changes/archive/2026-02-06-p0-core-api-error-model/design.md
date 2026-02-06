## Context

当前实现只存在 health endpoint；架构文档描述了 P0 应有的对象链路与建议 API。
本 change 只冻结“接口合同”，不做实现。

## Goals / Non-Goals

**Goals:**
- 明确 P0 API：Case/Evidence/SourceClaim/Assertion/Judgment 的最小读取与导航端点
- 明确 P0 写入接口的 Action-only 约束
- 明确统一错误模型（error_code、message、details、trace_id 等）

**Non-Goals:**
- 不实现完整鉴权系统（P0 仅做接口层预留）
- 不定义 P2/P3 的全量 API

## Decisions

### Decision 1: 错误模型采用 Problem Details 风格，但保留稳定 error_code

返回 shape 必须既可读也可机器处理，且在回归中稳定。

### Decision 2: P0 API 只覆盖 3 个 P0 用户流

避免 scope 漂移；其它端点进入 P1+。

## Risks / Trade-offs

- **[Risk] 过早冻结 API 导致后续难改】【Mitigation】版本化（v0）、并在 spec 中列出兼容策略。
