依赖顺序说明：A（需求冻结）→ B（P0 闭环与回归）→ C（P1 抽取与冲突）→ D（P2 监控/互操作/评测）→ E（P3 协作/规模化）。

## A. 需求研究（PRD 变成可验收合同）

- [ ] A1. 补齐 `docs/foundry/v0.2/prd.md`：Scope/Non-goals/User Stories/FR/NFR/Milestones
- [ ] A2. 冻结 P0 的 3 个用户流（离线可演示）+ DoD（Definition of Done）
- [ ] A3. 决定 P0 MVP ontology（最小实体/事件/关系集合）并写进 PRD
- [ ] A4. 合规工程化条款：robots/ToS、license_note、PII 最小化、retention（写进 PRD 与 design）

## B. P0（证据链闭环 + 离线回归）

> 目标：不用外网也能验证核心闭环与可回放性。

- [ ] B1. Repo 端口段统一为 87xx（应用 + 依赖全部映射到 87xx）
  - References: `docs/ops/ports.md`, `.env.example`, `docker-compose.yml`

- [ ] B2. 最小依赖 compose：Postgres + MinIO
  - Verify: `docker compose up -d postgres minio` + `docker compose ps`

- [ ] B3. `aegi-core` 权威数据层
  - 完成最小表：cases/artifact_identities/artifact_versions/chunks/evidence/source_claims/assertions/actions/tool_traces
  - 要求：所有 FK 列建索引；Alembic migrations 可升级/回滚
  - Verify: `cd code/aegi-core && uv sync --dev && uv pip install -e . && uv run pytest`

- [ ] B4. `aegi-mcp-gateway` 工具契约（先 contract 后实现）
  - `/tools/meta_search` `/tools/archive_url` `/tools/doc_parse`（允许先 stub）
  - 统一错误格式 + tool trace 记录结构

- [ ] B5. Core ↔ Gateway 调用链路
  - 规则：core 不直连外网；只通过 gateway
  - 每次关键写入都走 Action；每次工具调用写 tool_trace

- [ ] B6. 离线 fixtures（非做不可）
  - 创建固定 fixtures 包：归档产物 + 解析产物 + 预期 anchors + 预期 claims
  - 形成回归指标：anchor locate/drift、claim grounding

## C. P1（SourceClaim-first 抽取 + Assertion 融合 + 冲突/不确定性）

- [ ] C1. Chunking + anchor_set 冗余选择器（HTML/PDF）+ anchor_health
- [ ] C2. SourceClaim 抽取器（结构化输出，强制 selectors）
- [ ] C3. Assertion 融合与冲突集（允许多假设并存）
- [ ] C4. 最小 Workbench（读优先）：Evidence Vault / Claim Compare / Timeline（基础）

## D. P2（监控/互操作/评测产品化）

- [ ] D1. Watchlist + 定时增量更新（新版本 → 重新抽取 → diff）
- [ ] D2. MISP/OpenCTI/STIX 互操作（import/export mapping）
- [ ] D3. Eval-as-a-Product：指标与回归门禁（每次升级必须过回归）

## E. P3（协作与规模化）

- [ ] E1. RBAC/ABAC + case-scoped tokens
- [ ] E2. 派生索引（OpenSearch/Neo4j/Qdrant）与一键重建
- [ ] E3. HITL 审批流与审计回放 UI
