# Proposal: narrative_builder embedding 相似度升级

## Why

当前 `narrative_builder.py` 使用 `difflib.SequenceMatcher` 做 token-overlap 相似度，
对语义相近但措辞不同的 claims 聚类效果差。本地 vLLM BGE-M3 embedding 服务已运行，
`LLMClient.embed()` 已就绪，应当利用。

## What

- 新增 `_cosine_similarity()` 函数
- `build_narratives_with_uids` 新增 `embeddings` 参数（预计算向量字典）
- 新增 `abuild_narratives_with_uids` async 版本，自动调用 `embed_fn` 获取向量
- 未提供 embeddings 时 fallback 到 token-overlap（向后兼容）

## References

- ADR-001: baize-core 为主参考（STORM pipeline 模式）
- `LLMClient.embed()` → `http://localhost:8001/v1/embeddings`（BGE-M3）
