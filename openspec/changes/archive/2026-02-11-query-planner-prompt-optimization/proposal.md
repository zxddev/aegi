# Proposal: query_planner prompt 优化 + max_tokens 修复

## Why
1. 原 prompt 太简单，LLM 无法生成比规则版更精细的检索策略
2. max_tokens=512 导致 LLM 输出被截断，JSON 解析失败 fallback 到规则版

## What
- 优化 prompt：增加数据表用途说明、检索策略指引、步骤数要求
- max_tokens 512 → 1024
