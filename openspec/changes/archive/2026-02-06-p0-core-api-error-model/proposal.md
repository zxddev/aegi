## Why

P0 需要稳定的 API 合同与统一错误模型，才能让 Workbench/回归测试/后续多智能体编排依赖“可预测的接口”。同时 P0 的核心不变量要求 Action-only writes 与可追溯 tool_trace，需要在 API 层明确约束。

## What Changes

- 冻结 `aegi-core` P0 API 端点范围（围绕 3 个 P0 用户流）
- 冻结统一错误响应模型（结构化 error_code + 可机器消费）
- 冻结 Action-only writes 的 API 约束（哪些写入必须带 rationale/actor，如何记录 Action）

## Capabilities

### New Capabilities
- `core-api-contracts-p0`: P0 API surface for evidence/claims/judgments navigation
- `problem-details-error-model`: Unified error response shape with stable error codes
- `action-only-api-constraint`: API-level requirements for Action-only writes

### Modified Capabilities

（无）

## Impact

- `code/aegi-core/`：FastAPI routes/schemas + tests（实现阶段）
- `code/aegi-web/`：可基于该合同实现最小工作台（P1）
