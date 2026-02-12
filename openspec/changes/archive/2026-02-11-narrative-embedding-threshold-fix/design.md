# Design

在 build_narratives_with_uids 中，当 use_embeddings=True 时：
effective_threshold = max(similarity_threshold, 0.6)
聚类比较使用 effective_threshold 替代 similarity_threshold。
