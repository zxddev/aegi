# Proposal: coordination_detector embedding 支持

## Why
coordination_detector 使用 SequenceMatcher 做文本相似度，语义匹配能力弱。

## What
- `_pairwise_similarity` 新增 `embeddings` 参数，有则用 cosine，无则 fallback
- `detect_coordination` 新增 `embeddings` 参数透传
