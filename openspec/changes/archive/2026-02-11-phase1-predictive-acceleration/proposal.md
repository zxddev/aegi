# Proposal: predictive_signals 变化加速度

## Why
SignalScore 只有一阶导数 momentum，缺少二阶导数。

## What
- SignalScore 新增 `acceleration` 字段（二阶差分）
