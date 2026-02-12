<!-- Author: msq -->

## Decisions

1. SourceClaim 新增 `language/original_quote/translation/translation_meta`。
2. 翻译文本仅用于理解，不替代原文锚点。
3. 实体对齐输出必须带证据引用与置信度。

## Input / Output Contracts

- 输入：`SourceClaimV1[]`（含 quote/selectors）
- 输出：`SourceClaimV1[]`（补齐 language/translation）+ `EntityLinkV1[]`
- `EntityLinkV1` 最小字段：`canonical_id`、`alias_text`、`language`、`source_claim_uid`、`confidence`

## API Contract

- `POST /cases/{case_uid}/pipelines/detect_language`
- `POST /cases/{case_uid}/pipelines/translate_claims`
- `POST /cases/{case_uid}/pipelines/align_entities_cross_lingual`

所有响应必须返回 `trace_id`，且包含失败项列表。

## Fixtures

- `defgeo-multi-001`：中文/英文同实体
- `defgeo-multi-002`：俄文/英文同实体 + 歧义别名

## LLM / Rule Strategy

1. language detect 优先规则模型，LLM 仅补充低置信样本。
2. translate 阶段必须记录 `prompt_version` 与 `model_id`。
3. entity alignment 采用“规则候选 + LLM rerank”，并输出解释。

## Acceptance

1. 对齐输出必须可追溯到 source_claim_uid。
2. `cross_lingual_entity_link_f1 >= 0.88`（fixtures 基线）。
3. translation 不得覆盖 original_quote。
