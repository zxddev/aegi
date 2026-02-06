<!-- Author: msq -->

## Context

该 change 是所有功能 change 的前置依赖，目标是把“共享不可变部分”独立出来，避免后续冲突。

本 change 完成后，后续功能 AI 必须只实现业务逻辑，不再自行定义核心合同。

## Decisions

1. 共享模型字段先冻结：`SourceClaim`、`Assertion`、`Action`、`ToolTrace`，并预留多模态字段。
2. 共享错误模型先冻结：core 与 gateway 错误码语义一致。
3. 回归门禁先冻结：`anchor_locate_rate`、`claim_grounding_rate`、结构化报告输出。
4. LLM 治理合同前置：模型选择、prompt 版本、预算、降级、grounding 校验必须统一。
5. migration 所有权前置：所有共享 schema 迁移由 schema 协调者统一提交。

## Contract Outputs

以下是本 change 的必交付文件（后续 change 直接引用）：

- `code/aegi-core/src/aegi_core/contracts/schemas.py`
  - 定义共享输入输出 schema：SourceClaimV1、AssertionV1、HypothesisV1、NarrativeV1、EvidenceCitationV1。
- `code/aegi-core/src/aegi_core/contracts/errors.py`
  - 定义统一错误码枚举与 Problem Details 对象。
- `code/aegi-core/src/aegi_core/contracts/audit.py`
  - 定义 Action/ToolTrace 必填字段、trace_id 传播规则。
- `code/aegi-core/src/aegi_core/contracts/llm_governance.py`
  - 定义模型路由、prompt_version、budget_limit、fallback_policy、grounding_gate。
- `code/aegi-core/tests/contract_tests/`
  - 共享合同测试，所有功能 change 必须通过。

## LLM Governance Contract

必须统一以下规则：

1. **模型路由**：抽取/分类/推理任务使用不同模型层级，禁止在功能分支私自改模型默认值。
2. **Prompt 版本**：每个 LLM 调用必须带 `prompt_version`，结果需记录在 ToolTrace/Action outputs。
3. **成本门禁**：每个 case 有 token/cost budget，超预算时降级到规则路径或人工复核。
4. **Grounding 门禁**：LLM 输出若无证据引用，不得标记为 FACT。
5. **故障降级**：模型不可用时必须返回结构化降级结果，不得 silent fail。

## Migration Ownership

1. foundation 阶段统一提交共享 schema migration（一次性覆盖 P1-P3 公共字段/表）。
2. 后续功能 AI 禁止直接新增 Alembic revision。
3. 若发现 schema 缺口，提交 `schema-change-request` 到合并协调者，由 schema 协调者集中处理。

## Multimodal Reserved Fields

为后续图像/视频/音频预留字段，不在本阶段实现推理能力：

- Evidence/Chunk 增加 `modality`（text/image/video/audio）
- 预留 `segment_ref` 与 `media_time_range`（可空）

## Fixture Convention (Global)

统一 fixtures 命名与 manifest 扩展，避免各功能分支各自发明格式：

1. fixture_id 采用 `defgeo-<domain>-<scenario>-<nnn>` 规范。
2. 兼容现有 `defgeo-001/002`，通过 manifest `aliases` 字段映射。
3. manifest 必须包含 `scenario_type`（claim/ach/narrative/kg/chat/forecast/quality）。
4. 新增字段须向后兼容，旧 tests 不改即可读取。

## Definition of Done

1. 共享合同文件齐全且有测试覆盖。
2. LLM 治理合同可执行（有测试或静态校验）。
3. migration 所有权规则写入并行协议。
4. 所有后续 change 的 proposal 明确依赖本 change。

## Non-Goals

- 不实现具体业务能力（多语言/ACH/叙事等）。
- 不引入新外部索引系统。
