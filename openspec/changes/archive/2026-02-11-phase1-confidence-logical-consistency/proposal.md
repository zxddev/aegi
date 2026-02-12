# Proposal: confidence_scorer 逻辑一致性维度

## Why
score_confidence 缺少 assertion 间逻辑矛盾检测维度。

## What
- 新增 `_logical_consistency` 维度函数
- 检查 confirmed vs denied 矛盾 + 时间顺序矛盾
