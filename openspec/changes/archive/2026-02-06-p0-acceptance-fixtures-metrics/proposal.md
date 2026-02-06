## Why

P0 采用 `fixtures-only` 策略，必须把“离线可回归”做成硬门禁：固定 fixtures 包、固定测量方法、固定指标阈值。否则后续锚点/抽取/融合升级会不可控，且无法证明 Evidence-first/Anchor contract 仍然成立。

## What Changes

- 定义 P0 离线 fixtures pack 的组成、目录结构与 manifest 规范
- 定义 P0 回归指标：anchor_locate_rate、drift_rate、claim_grounding_rate 等
- 定义 P0 的最低阈值与失败处理（gate）
- 定义“可重复测量”的测试场景（无外网、无第三方服务）

## Capabilities

### New Capabilities
- `offline-fixtures-pack`: Offline fixtures pack + manifest for P0 acceptance
- `regression-metrics-thresholds`: Metrics definitions + thresholds + gating behavior

### Modified Capabilities

（无）

## Impact

- 测试与数据：`code/aegi-core/tests/fixtures/`（将由实现阶段创建）
- 质量门禁：后续 extraction/anchors/fusion 的升级都必须通过该回归
