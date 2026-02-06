# AEGI Foundry 实现架构（v0.2 / 开发参考）
日期：2026-02-05  
目标读者：后端/数据/基础设施/前端（需要对接 API 合同）

> 这是“怎么把 PRD + 技术架构落成可写代码”的最小可执行蓝图。  
> 推荐策略：先把 v0.2 的数据结构与闭环打通，再加性能索引；不要一上来就分布式和全家桶。

---

## 0. 与现有仓库的关系（别推倒重来）

### 0.1 已有资产（能直接复用）
- `code/aegi-core/`：证据链、策略闸门、审计回放、LangGraph 编排、部分对象写入接口。
- `code/aegi-mcp-gateway/`：工具统一入口、Scrape Guard（域名策略/robots/限流/缓存/审计）、适配器（SearxNG/Unstructured/ArchiveBox）。

### 0.2 v0.2 的关键增量（必须补齐）
1. **SourceClaim-first**：Chunk→SourceClaim→Assertion 两阶段。
2. **Identity/Version 拆分**：ArtifactIdentity vs ArtifactVersion；引用必须钉到 version。
3. **强锚点协议**：anchor_set + anchor_health，进入 Gate 与 UI。
4. **Ontology 兼容契约**：compatibility_report / migration_plan / case pinning。
5. **Coverage breakdown**：质量×多样性×独立互证×时效性；防转载堆量刷覆盖。
6. **合规工程化**：license_note、retention、PII 最小化、导出脱敏策略。

---

## 1. 代码组织建议（P0：模块化单体）

### 1.1 推荐落地路径（最省工且可回归）
**方案 A（推荐）：在 `aegi-core` 内实现 Foundry 后端能力**
- 优点：复用现有 Policy/Audit/Evidence/Orchestration；测试体系已存在。
- 缺点：短期内 repo 更大，但仍可用模块边界管理。

**方案 B：新建 `aegi-foundry` 服务**
- 优点：更干净的边界。
- 缺点：要搬运一堆内核模块，短期重复劳动更多。

P0 建议选方案 A，P1/P2 再抽成独立服务（Never break userspace）。

### 1.2 `aegi-core` 内部模块建议（示例）
在 `aegi_core/` 下新增/扩展：
- `schemas/`：新增 `artifact_identity.py`、`artifact_version.py`、`anchor.py`、`source_claim.py`、`assertion.py`、`ontology_change.py`、`coverage.py`
- `evidence/`：anchor_set/health 解析与定位、EvidencePackage 组装、引用闭环校验升级（claim-aware）
- `orchestration/`：新增 graphs：
  - `ingest_graph.py`
  - `extraction_graph.py`（SourceClaimExtract + Fusion）
  - `monitoring_graph.py`
- `policy/`：导出/工具调用/高风险动作策略（case-scoped token）
- `api/`：
  - `/cases`、`/evidence`、`/source_claims`、`/assertions`、`/actions`、`/audit`、`/export`
- `storage/`：Postgres 表/索引、MinIO storage_ref、派生索引重建触发器（先留接口）

---

## 2. 数据库与迁移（Postgres：权威源）

> 目标：把“引用闭环、版本化、可回放”写进数据结构，不要靠约定。

### 2.1 表清单（P0 必备）
建议在 `aegi_core` schema 内新增/调整：
- `cases`
- `ontology_versions`
- `artifact_identities`
- `artifact_versions`
- `chunks`（含 `anchor_set`、`anchor_health`）
- `evidence`（含 `license_note`、`pii_flags`、`retention_policy`）
- `source_claims`
- `assertions`
- `assertion_source_claims`（关联表）
- `assertion_conflicts`
- `entities` / `events` / `relations`
- `merge_decisions` / `entity_redirects`
- `actions` / `action_events`
- `audit_*`（tool traces / model traces / policy decisions）

### 2.2 关键索引（别偷懒）
- FK 列必须手工建索引（Postgres 不会自动建）：
  - `artifact_versions(artifact_identity_uid)`
  - `chunks(artifact_version_uid)`
  - `evidence(chunk_uid)`
  - `source_claims(evidence_uid, chunk_uid, artifact_version_uid)`
  - `assertion_source_claims(assertion_uid, source_claim_uid)`
- 查询热路径：
  - Evidence Vault：`evidence(published_at, domain, language, score)`
  - Claim/Assertion：`source_claims(predicate, modality, speaker)`（可用表达式/GIN( JSONB )）
  - Timeline：`events(time_start, time_end)` + `assertions(time_start, time_end)`

### 2.3 兼容性与迁移策略（不破坏已有接口）
现有系统若已有 `artifact_uid/chunk_uid/evidence_uid`：
- **保留 `artifact_uid` 语义为 “version UID”**（即 `artifact_version_uid`），新增 `artifact_identity_uid` 字段。
- 新增 `artifact_identities` 表；对历史数据做 backfill：
  - identity：由 canonical_url/publisher 归一化生成
  - version：沿用原 artifact_uid
- API 层保持旧端点可用，同时增加新端点与字段（向后兼容）。

---

## 3. API 合同（FastAPI / REST 优先）

### 3.1 资源分组
- Case：`/cases`
- Ontology：`/ontology`
- Evidence：`/evidence`、`/artifacts`、`/artifact_versions`
- Objects：`/entities`、`/events`、`/relations`、`/source_claims`、`/assertions`
- Graph/Timeline：`/graph/*`、`/timeline/*`
- Actions/HITL：`/actions`、`/reviews`
- Audit/Replay：`/audit/*`、`/replay/*`
- Export：`/export/*`

### 3.2 P0 必备端点（示例）
- `POST /cases`
- `POST /cases/{case_id}/runs/ingest`
- `POST /cases/{case_id}/runs/extract`（产出 source_claims + assertions）
- `GET /cases/{case_id}/evidence`
- `GET /evidence/{evidence_uid}`（返回 chunk + artifact_version + anchor_set + anchor_health）
- `GET /source_claims/{uid}`（quote + selectors + modality + speaker + 证据链）
- `GET /assertions/{uid}`（assertion + supporting/counter claims）
- `POST /actions`（merge/edit/resolve_conflict/approve_judgment/export）
- `GET /cases/{case_id}/replay/{trace_id}`
- `POST /export/evidence_package`

### 3.3 合同要点
- 所有返回必须带 `trace_id`（可用于回放）。
- 所有“发布/导出/合并”必须走 Action 并产出审计记录。
- Judgment/Assertion 默认展示 supporting_source_claims（独立来源数）与 anchor_health。

---

## 4. Pipeline 实现要点（LangGraph）

### 4.1 IngestGraph（外联治理强制）
实现建议：
- Node 输入输出全结构化（Pydantic）。
- Tool 调用统一包装：注入 `trace_id/case_id` header；记录 ToolTrace；输出净化。
- Parse/Chunk 时生成 anchor_set；写入 anchor_health 初始值。

### 4.2 SourceClaimExtract（抽取器契约）
抽取器输出必须包含：
- `quote`（原文片段，不改写）
- `quote_selectors`（TextQuote/TextPosition）
- `modality`、`speaker`、`attribution_chain`
- `claim_slots`（subject/predicate/object/value/time_range）

### 4.3 AssertionFusion（融合与可解释性）
最小可用实现（不依赖“大模型主观”）：
1. blocking：按 `(subject, predicate, time_bucket)` 分桶
2. within-bucket clustering：按 object/value 相似（字符串/数值/枚举）+ 来源独立性
3. 输出 assertion：选择代表值 + 计算 confidence + 记录 supporting/counter claims
4. rationale：结构化（规则命中、冲突原因、缺口）

### 4.4 ConflictDetector（双层）
- claim-level：互斥值/互斥时间窗/互斥地点
- assertion-level：融合后仍互斥 → 写入 `assertion_conflicts`

---

## 5. CoverageGate（防刷覆盖）

实现建议：
- 转载/镜像检测：按 canonical_url/publisher/content_sha256/文本相似度去重，避免堆量。
- breakdown：
  - 质量：来源可靠性/信息可信度（Evidence 字段）
  - 多样性：publisher/source_type/语言/地区
  - 互证：关键字段一致性（claim slots 对齐）
  - 时效：是否落在 case time_window
- 输出 GapQuery：缺官方/缺一手/缺地理证据/缺时间窗等明确原因。

---

## 6. 强锚点定位（anchor_set）落地

实现建议：
- `anchor.locate()`：输入 `artifact_version_uid + anchor_set`，输出定位结果（span/bbox）与 `anchor_health`。
- 每次导出/发布前重新 locate 校验（防漂移）。
- 锚点破坏处理：
  - FACT 自动降级为 INFERENCE 或触发 HITL 修复
  - Evidence Vault UI 提示“此引用已漂移/回退”

---

## 7. Ontology 变更机制（兼容性契约）

落地建议：
- `ontology_versions` 存：
  - `version`、`hash`、`author`、`created_at`
  - `compatibility_report`（JSONB）
  - `migration_plan`（JSONB）
- Action：
  - `propose_ontology_change`（生成 compat report）
  - `apply_ontology_change`（需要审查）
  - `upgrade_case_ontology`（case pinning）

---

## 8. 合规工程落地

### 8.1 retention / 删除
- `retention_policy`：case 默认 + evidence override
- 清理作业：按策略删除/脱敏 Evidence/Export（保留审计最小记录）

### 8.2 PII
- Evidence 入库前做 PII 扫描（轻量规则 + 可选模型）
- 对象层写入前最小化：不把 PII 直接写进 Entity/Assertion
- 导出默认脱敏（策略可配置）

### 8.3 license
- Evidence/ArtifactVersion 保存 license_note 与限制
- ExportService 按限制裁剪内容（最小引用片段 + 元数据）

---

## 9. 测试与评测（Eval-first 不是口号）

### 9.1 单元/集成测试（建议）
- anchor 定位：HTML/PDF 漂移用例
- claim extraction：modality/speaker/quote_selectors
- fusion：同义/数值/时间窗冲突
- coverage：转载堆量不计数
- replay：同一输入可重放（ToolTrace/ActionLog 一致）

### 9.2 回归集（建议）
- 固定一组 case fixtures（真实网页快照/WARC/PDF）做离线回归
- 指标趋势必须可视化（至少 markdown 报告 + diff）

---

## 10. 部署参考（P0 最小闭环）

最小依赖：
- Postgres
- MinIO
- aegi-mcp-gateway
- aegi-core（Foundry 能力实现于此）

建议以 docker-compose 开始；上线前再拆 IAM/WAF/独立索引服务。
