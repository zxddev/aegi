<!-- Author: msq -->

## 1. 共享合同文件（文件级输出）

- [ ] 1.1 创建 `code/aegi-core/src/aegi_core/contracts/schemas.py`（SourceClaimV1/AssertionV1/HypothesisV1/NarrativeV1）
- [ ] 1.2 创建 `code/aegi-core/src/aegi_core/contracts/errors.py`（统一 error_code + Problem Details）
- [ ] 1.3 创建 `code/aegi-core/src/aegi_core/contracts/audit.py`（Action/ToolTrace 字段与 trace 传播）

## 2. LLM 治理合同

- [ ] 2.1 创建 `code/aegi-core/src/aegi_core/contracts/llm_governance.py`（model routing/prompt_version/budget/fallback）
- [ ] 2.2 定义 LLM grounding gate（无证据引用不得输出 FACT）
- [ ] 2.3 定义超预算与模型不可用的降级输出结构

## 3. 迁移所有权与 schema 统一

- [ ] 3.1 在 foundation 阶段一次性提交共享 Alembic migration（包含 P1-P3 公共字段）
- [ ] 3.2 写明后续功能 change 禁止直接新增 migration
- [ ] 3.3 增加 `schema-change-request` 处理流程（由 schema 协调者统一合并）

## 4. 多模态预留

- [ ] 4.1 在共享 schema 预留 `modality`（text/image/video/audio）
- [ ] 4.2 预留 `segment_ref` 与 `media_time_range`（可空）

## 5. 共享验证

- [ ] 5.1 创建 `code/aegi-core/tests/contract_tests/test_schemas_contract.py`
- [ ] 5.2 创建 `code/aegi-core/tests/contract_tests/test_error_model_contract.py`
- [ ] 5.3 创建 `code/aegi-core/tests/contract_tests/test_llm_governance_contract.py`
- [ ] 5.4 固化回归报告格式（json + markdown）

## 6. 依赖输出

- [ ] 6.1 输出“后续 change 必须依赖清单”（功能 -> 合同项映射）
- [ ] 6.2 在 `openspec/parallel-ai-execution-protocol.md` 登记本 change 为全局 Gate-0

## 7. Fixtures 规范

- [ ] 7.1 定义 fixture 命名规范（`defgeo-<domain>-<scenario>-<nnn>`）
- [ ] 7.2 扩展 `tests/fixtures/manifest.json` 规范（增加 `scenario_type`、`aliases`）
- [ ] 7.3 提供 manifest 向后兼容约束（兼容 `defgeo-001/002`）
- [ ] 7.4 输出 fixture 使用映射表（openspec 场景 -> fixture_id）
