<!-- Author: msq -->

## 1. 抽取器（SourceClaim）

- [x] 1.1 在 `services/claim_extractor.py` 实现 `extract_from_chunk`（输入 chunk，输出 SourceClaimV1[]）
- [x] 1.2 增加 selectors 强校验（空 selectors 直接拒收）
- [x] 1.3 为抽取调用接入 `llm_governance`（model_id/prompt_version/budget）

## 2. 融合器（Assertion）

- [x] 2.1 在 `services/assertion_fuser.py` 实现 `fuse_claims`（输出 AssertionV1[]）
- [x] 2.2 实现冲突识别（值冲突 + modality 冲突）
- [x] 2.3 保留冲突，不允许覆盖旧 Assertion

## 3. API 与审计

- [x] 3.1 增加 `POST /cases/{case_uid}/pipelines/claim_extract`
- [x] 3.2 增加 `POST /cases/{case_uid}/pipelines/assertion_fuse`
- [x] 3.3 所有 pipeline 调用记录 Action + ToolTrace + trace_id

## 4. Fixtures 与测试

- [x] 4.1 增加 `tests/fixtures/defgeo-claim-001`
- [x] 4.2 增加 `tests/fixtures/defgeo-claim-002`（冲突场景）
- [x] 4.3 新增 `test_claim_extraction_pipeline.py`
- [x] 4.4 新增 `test_assertion_fusion_pipeline.py`

## 5. 验收

- [x] 5.1 验证 `claim_grounding_rate >= 0.97`
- [x] 5.2 验证冲突集输出稳定
