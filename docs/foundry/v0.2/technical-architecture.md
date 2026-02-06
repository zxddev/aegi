# AEGI Foundry 技术架构（v0.2）
日期：2026-02-05  
目标读者：后端/架构/安全/数据工程/前端（Workbench）

> 核心合同：把 OSINT 的“证据、说法、断言、判断、动作”拆成可审计、可回放、可计算的数据结构。  
> 强制链路：`Judgment → Assertion → SourceClaim → Evidence → Chunk(anchor_set) → ArtifactVersion → ArtifactIdentity`

---

## 0. 约束与不变量（不遵守就必炸）

1. **Object-first**：系统的一等公民是对象（Entity/Event/Relation/SourceClaim/Assertion），不是长报告。
2. **Evidence-first + Archive-first**：外部世界进入系统必须先固化为 ArtifactVersion，再切 Chunk，再形成 Evidence；禁止“看网页直接写结论”。
3. **SourceClaim-first**：平台必须能回答“来源到底怎么说的”，否则审计/客户信任会崩。
4. **Deterministic IDs（身份 vs 版本）**：动态网页必然变化，必须拆 identity/version；引用必须钉到 version。
5. **强锚点 + 健康度**：引用定位是合同，不是 best-effort；必须可检测漂移与回退。
6. **Action-only writes**：任何改“世界状态”的写入只能走 Action（审计/回滚/授权）。
7. **派生索引可重建**：Postgres 是权威源；图/全文/向量都是派生索引，必须能一键重建。
8. **Deny-by-default**：模型/工具/导出/高风险动作全部需要策略引擎显式放行。

---

## 1. 分层与平面（Workbench / Control / Data / Tool）

```
┌───────────────────────────────────────────────────────────────────┐
│                        Analyst Workbench (UI)                      │
│  Evidence Vault | Claim Compare | Timeline | Graph | Judgments |   │
│  Watchlist | HITL Reviews | Replay | Export                          │
└───────────────────────────────┬───────────────────────────────────┘
                                │
┌───────────────────────────────┴───────────────────────────────────┐
│                       Control Plane (API)                          │
│  IAM/RBAC/ABAC | Policy Engine | Case/Ontology/Action/Query/Audit   │
│  Export Service | Webhook/Signals                                   │
└───────────────────────────────┬───────────────────────────────────┘
                                │ jobs/events
┌───────────────────────────────┴───────────────────────────────────┐
│                        Data Plane (Pipelines)                      │
│  LangGraph Orchestrator + Workers                                   │
│  Ingest → ClaimExtract → Fuse → Resolve → Validate → Index → Analyze │
└───────────────────────────────┬───────────────────────────────────┘
                                │ tool calls (governed)
┌───────────────────────────────┴───────────────────────────────────┐
│                          Tool Plane (MCP)                          │
│  MCP Gateway: allow/deny | robots/ToS | rps/concurrency | cache     │
│  sanitize(schema whitelist) | audit transcript                       │
└───────────────────────────────────────────────────────────────────┘
```

**P0 依赖收敛（小团队可运维）**
- Postgres（权威源 + FTS + JSONB，必要时 pgvector）
- MinIO（ArtifactVersion 快照：WARC/HTML/PDF/截图/导出包）
- MCP Gateway（外联治理与工具协议）

**P1+ 派生索引（加速，不是前置条件）**
- OpenSearch（全文）
- Qdrant（向量）
- Neo4j（图查询）

---

## 2. 权威数据模型（关键对象与关系）

### 2.1 实体关系（概念 ER）

```
Case
 ├─ OntologyVersion (pinned)
 ├─ ArtifactIdentity 1─N ArtifactVersion
 │    └─ ArtifactVersion 1─N Chunk 1─N Evidence
 │          └─ Chunk 1─N SourceClaim N─M Assertion
 │                 └─ Assertion N─M Conflict
 ├─ Entity/Event/Relation (from Assertions)
 ├─ Judgment (references Assertions + SourceClaims)
 ├─ WatchItem (references gaps/Assertions/SourceClaims)
 └─ ActionLog (the only mutation path)
```

### 2.2 必备字段（只列硬约束）

**ArtifactIdentity**
- `artifact_identity_uid`（稳定身份）
- `canonical_url`、`publisher`、`title_normalized`、`first_seen_at`

**ArtifactVersion**
- `artifact_version_uid`（不可变版本）
- `artifact_identity_uid`（FK）
- `content_sha256`、`fetched_at`、`renderer_version`
- `storage_ref`（MinIO key/WARC ref）

**Chunk**
- `chunk_uid`
- `artifact_version_uid`（FK）
- `anchor_set`（多选择器冗余）
- `anchor_health`（可定位/漂移/回退）
- `text`（或 storage ref；视成本/合规）

**Evidence**
- `evidence_uid`
- `chunk_uid`（FK）
- `source_type`、`language`、`published_at`、`score`
- `license_note`、`retention_policy`、`pii_flags`

**SourceClaim（贴原文）**
- `source_claim_uid`
- `evidence_uid` / `chunk_uid` / `artifact_version_uid`
- `quote` + `quote_selectors[]`（TextQuote/TextPosition）
- `speaker`、`attribution_chain[]`
- `modality`（confirmed/likely/alleged/denied/unknown）
- `claim_slots`（subject/predicate/object/value/time_range），但不强制融合归一
- `provenance`（extractor_version/model/trace_id）

**Assertion（融合后可计算）**
- `assertion_uid`
- `subject_kind/subject_uid` + `predicate` + `object_kind/object_uid/value`
- `time_range`（含 approx/raw_text）
- `confidence`
- `supporting_source_claims`（关联表）
- `provenance`（claim_extractor_version/fuser_version/model/trace_id）

**Action**
- `action_uid`、`action_type`、`payload`、`actor`、`approved_by`、`trace_id`
- Action 是写入与迁移的唯一入口（可回滚/可审计）

---

## 3. ID 方案（Deterministic：身份 vs 版本）

### 3.1 设计原则
- **identity**：尽量稳定（同一来源“是谁”）。
- **version**：严格不可变（某次采集“是什么”）。
- 引用必须钉到 version；identity 主要用于聚合、展示、去重、版本历史。

### 3.2 推荐 UID 生成
- `artifact_identity_uid = hash(normalize(canonical_url) + publisher + stable_keys)`
- `artifact_version_uid = hash(content_sha256 + fetched_at_bucket + renderer_version)`（或 ULID + content_sha256 作为校验）
- `chunk_uid = hash(artifact_version_uid + anchor_set + quote_hash)`

> 注意：不要把 fetched_at 精确到毫秒塞进 hash 造成“每次都新版本”；用 content_sha256 作为核心，时间只做辅助。

---

## 4. 强锚点（anchor_set）协议与健康度

### 4.1 anchor_set（多选择器冗余）
- HTML：`xpath`/`css_selector` + `TextQuoteSelector(prefix/exact/suffix)` + `TextPositionSelector(start/end)`
- PDF：`page` + `bbox` + `TextQuoteSelector`
- 媒体：`timestamp_range` + `transcript_quote`

### 4.2 anchor_health（必须记录）
- `locate_ok`：当前版本能否定位到原文
- `drift_detected`：定位结果与 quote 不一致/偏移超阈值
- `fallback_used`：是否回退到 quote 搜索
- `confidence`：0–1（用于 UI 提示与 Gate）

### 4.3 漂移处理策略
1. 优先用结构选择器定位（xpath/bbox）。
2. 校验 quote（前后缀+exact）一致性。
3. 失败则回退到全文 quote 搜索（记录 fallback）。
4. 若仍失败：标记 anchor_broken，阻断“FACT”级判断或触发 HITL 修复。

---

## 5. 数据面流水线（LangGraph：可回放状态机）

### 5.1 IngestGraph（Archive-first）
`Search → SelectURLs → Archive → Fetch/Crawl → Parse/OCR/Translate → Chunk(anchor_set) → EvidenceCreate → CoverageCheck`

关键点：
- 外联全部走 MCP Gateway（domain policy / robots / rps / cache / audit）。
- 先固化 ArtifactVersion（WARC/HTML/PDF），再解析。
- EvidenceCreate 必须写入 license/PII/retention 元数据。

### 5.2 ExtractionGraph（SourceClaim-first）
`SourceClaimExtract → Normalize(Time/Geo on slots) → AssertionFusion → ConflictDetect → Persist`

关键点：
- **SourceClaimExtract 不改写 quote**（只抽取 selectors/modality/speaker）。
- Fusion 输出结构化 rationale（为什么融合、哪些 claim 支撑、哪些是反证）。
- 冲突必须在 claim-level 与 assertion-level 都可追踪。

### 5.3 ResolutionGraph（可解释的消歧融合）
`CandidateGen(blocking/embedding/co-occur) → Scoring(rule/stat/optional LLM) → Cluster → MergeAction(HITL gated)`

关键点：
- 合并不抹历史：`redirects(old→new)` + 查询层 resolve。
- 高风险对象（军队单位/设施/装备）默认 HITL。

### 5.4 Validation/Gates（把质量变成硬规则）
- 引用闭环：Judgment/Assertion 必须回溯到 SourceClaim → Evidence → ArtifactVersion。
- 锚点健康度：anchor_locate_rate / drift_rate 达标才允许发布/导出。
- Coverage：质量×多样性×独立互证×时效性 score breakdown；防“转载堆量刷覆盖”。
- Timeline consistency：规则 +（可选）Z3 输出可解释违反约束。

### 5.5 MonitoringGraph（Watchlist 增量再分析）
`Signal Trigger → Incremental QuerySet → IngestGraph → ExtractionGraph → Update AnalysisPackage(versioned)`

---

## 6. Ontology（合同）与迁移契约

### 6.1 IaC + 运行时加载
- `ontology/`（YAML/JSON）：object_types/link_types/properties/constraints/actions。
- 启动校验 → 写入 `ontology_versions`（hash + version + author + created_at）。

### 6.2 兼容性契约（必须）
- `compatibility_report`：检测 breaking changes（删字段/改类型/改枚举值/改谓词语义）。
- `deprecate → migrate → remove`：先弃用，再迁移 backfill，再删除。
- `case pinning`：case 固定 ontology_version；升级必须 Action 审批。

---

## 7. 安全、合规与治理（工程执行点）

### 7.1 策略引擎（Control Plane）
- 模型调用：allowed_models、预算、超时、降级。
- 工具调用：allowed_tools、tool风险等级、domain policy、并发/rps。
- 导出：显式授权/HITL + 脱敏策略。

### 7.2 MCP 工具安全（Tool Plane）
- tool server/user/case 令牌隔离
- 参数与输出 schema 校验 + 字段白名单净化
- ToolTrace transcript 可回放（脱敏/加密/访问控制）

### 7.3 合规（版权/许可/隐私）
- retention：按 case/来源配置保留期，自动清理。
- PII：对象层最小化；导出默认脱敏；删除/更正请求可审计。
- license：Evidence/Export 保留 license_note 与限制；受限来源最小保存。

---

## 8. 可观测性与可运维性

### 8.1 必备观测
- Trace：跨服务 trace_id（API→Graph→Tool→Storage）
- Metrics：
  - crawl success/block/cache hit
  - anchor_locate_rate/drift_rate
  - claim_grounding_rate/citation_hit_rate
  - coverage breakdown（质量/多样性/互证/时效）
  - latency/cost
- Logs：结构化日志按 case_id/trace_id 可检索

### 8.2 重建能力
- OpenSearch/Qdrant/Neo4j 必须可从 Postgres + MinIO 一键重建。
- Export 包必须包含必要映射（anchor_map/claim_map/ontology_version）以便第三方复核。

---

## 9. 与现有代码的映射（落地参考）

- 后端基础闭环：`code/aegi-core/`（Evidence/Policy/Audit/LangGraph 编排已有基础）
- 工具治理出口：`code/aegi-mcp-gateway/`（Scrape Guard/工具注册/适配器/审计）
- Foundry v0.2 的增量：引入 `SourceClaim`、identity/version UID、强锚点协议、Ontology 兼容契约、Coverage breakdown 与 Eval-as-product 的 UI/API 合同。
