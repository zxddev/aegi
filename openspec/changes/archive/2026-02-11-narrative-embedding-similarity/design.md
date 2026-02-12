# Design: narrative_builder embedding 相似度

## 变更范围

仅 `src/aegi_core/services/narrative_builder.py`，无新依赖。

## 接口变更

### `build_narratives_with_uids` 新增参数
```python
embeddings: dict[str, list[float]] | None = None
```
- 提供时：用 cosine similarity 比较 claim 向量
- 未提供时：fallback 到 `_token_similarity`（SequenceMatcher）

### 新增 `abuild_narratives_with_uids`
```python
async def abuild_narratives_with_uids(
    claims, *, embed_fn=None, ...
) -> tuple[list[NarrativeV1], dict[str, list[str]]]:
```
- `embed_fn`: async callable(text) -> list[float]，通常传 `LLMClient.embed`
- 内部 `asyncio.gather` 批量获取 embedding 后委托同步版本

## 降级策略

embed_fn 为 None 或 embeddings 中缺少某 claim 的向量时，自动 fallback 到 token-overlap。
