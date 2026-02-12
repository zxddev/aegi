<!-- Author: msq -->

## Why

并行开发多个能力前，必须先冻结公共合同，避免各 AI 在数据结构、审计、错误模型、LLM 策略上分叉。

当前最大风险不是功能实现，而是并行开发导致的合同漂移：

- schema 不一致（SourceClaim/Assertion 派生字段不兼容）
- Alembic 分叉（多个分支同时生成 migration）
- LLM 输出不可控（提示词、成本、降级、grounding 门禁不统一）
- 合并冲突无归口（router/依赖/迁移链）

## What Changes

- 冻结公共基础能力：证据链不变量、Action-only、ToolTrace、统一错误模型、回归指标门禁。
- 新增 LLM 治理合同：模型路由、prompt 版本、预算门禁、grounding 门禁、降级策略。
- 新增 migration 所有权合同：foundation 阶段一次性完成共享 schema migration，后续功能 AI 不直接改 migration。
- 冻结共享输出文件（文件级合同），供所有后续 change 直接引用。

## Capabilities

### New Capabilities

- `foundation-common-contracts`
- `llm-governance`
- `schema-migration-ownership`
- `multimodal-contract-reserved`

### Modified Capabilities

- `evidence-first-ingest`
- `source-claim-first`
- `tool-governance`
- `offline-regression`

## Impact

- `code/aegi-core/src/aegi_core/contracts/schemas.py`（共享 Pydantic schema 合同）
- `code/aegi-core/src/aegi_core/contracts/errors.py`（统一错误码与错误响应结构）
- `code/aegi-core/src/aegi_core/contracts/audit.py`（Action/ToolTrace 审计字段合同）
- `code/aegi-core/src/aegi_core/contracts/llm_governance.py`（模型路由/预算/prompt 版本/降级）
- `code/aegi-core/tests/contract_tests/*`（公共合同测试）
- `code/aegi-core/alembic/versions/*`（由 schema 协调者统一提交的共享 migration）
- `openspec/parallel-ai-execution-protocol.md`（并行执行与合并协议）
