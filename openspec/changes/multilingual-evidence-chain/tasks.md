<!-- Author: msq -->

## 1. 数据契约

- [ ] 1.1 在共享 schema 中启用 `language/original_quote/translation/translation_meta`
- [ ] 1.2 在 `source_claim.py` 对应映射字段并完成兼容读取

## 2. 语言与翻译流水线

- [ ] 2.1 新增 `services/multilingual_pipeline.py`（detect + translate）
- [ ] 2.2 所有 LLM 调用接入 governance（budget/prompt_version）
- [ ] 2.3 翻译失败输出结构化错误，不阻塞原文 claim 保留

## 3. 跨语言实体对齐

- [ ] 3.1 新增 `services/entity_alignment.py`（候选生成 + rerank）
- [ ] 3.2 输出 `EntityLinkV1` 并记录证据引用
- [ ] 3.3 加入歧义别名冲突标记

## 4. API 与测试

- [ ] 4.1 增加 3 个 pipeline API（detect/translate/align）
- [ ] 4.2 新增 `test_multilingual_pipeline.py`
- [ ] 4.3 新增 `test_cross_lingual_entity_alignment.py`

## 5. 验收

- [ ] 5.1 fixtures 上 `cross_lingual_entity_link_f1 >= 0.88`
- [ ] 5.2 验证 original_quote 保真与可回源
