# Spec: narrative_builder embedding 相似度

## Requirements

- `_cosine_similarity` MUST return 0.0 for zero-norm vectors
- `build_narratives_with_uids` MUST accept optional `embeddings` parameter
- 未提供 embeddings 时 MUST fallback 到 token-overlap（SequenceMatcher）
- `abuild_narratives_with_uids` MUST batch-embed via `asyncio.gather`
- 所有现有测试 MUST 保持绿灯（向后兼容）

## Verification

- 193 passed, 15 skipped, 0 failed (2026-02-08)
- ruff check: clean
- ruff format: clean
