# Proposal: narrative 聚类 embedding 阈值修复

## Why
embedding cosine similarity 数值分布（0.3-0.8）与 token-overlap（0.0-0.5）不同，
使用相同阈值 0.35 导致 embedding 路径聚类过松，不相关 claims 被错误聚合。

## What
embedding 路径自动提高阈值下限到 0.6。
