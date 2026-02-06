# 超越 Palantir 的多智能体情报工作台（AEGI Foundry）完整架构设计（v0.2）
日期：2026-02-05

> 目标：构建一个以 **Ontology/Object-first** 为核心的 OSINT 情报工作台。
> 
> - 主界面不是“长报告”，而是：**证据库（Evidence Vault）+ 时间线（Timeline）+ 关系图谱（Graph）+ 关键判断（Key Judgments）+ 观察指标（Watchlist）**。
> - 所有结论必须可回溯到“可归档证据链”：`Judgment → Assertion → SourceClaim → Evidence → Chunk(anchor) → Artifact(version)`。
> - 多智能体用于：自动拆解议题、自动搜集资料、自动抽取对象与关系、自动补洞与红队审查、自动生成可审计判断。

---

## 0. 先说清楚边界（合规与安全红线）

### 0.1 输出边界（必须严格执行）
1. **仅基于开源情报（OSINT）**：所有材料来自公开互联网或用户提供材料。
2. **只做研究分析与不确定性呈现**：输出必须区分事实/推断/假设，并明确证据缺口。
3. **尊重 robots.txt 与站点 ToS**：外联访问必须走治理出口（MCP Gateway），并记录 ToS/robots 证据。
4. **版权/许可优先**：归档与再分发必须遵守版权与数据许可；对受限来源默认仅保留必要引用片段/摘要 + 元数据（保留 license_note），导出需显式授权与水印/免责声明。
5. **隐私与个人信息（PII）最小化**：外部材料进入 evidence zone 可存原文用于审计，但进入对象层必须最小化；支持 case 级 retention、删除/脱敏与导出过滤。

### 0.2 为什么要强调这些边界
- 这不是道德口号，而是工程可控性：只要允许“无证据/无引用/不可回放”的输出进入主界面，平台就会迅速坍塌为“幻觉写作器”。
- 只要外联不治理（robots/限流/缓存/审计），你就会在大规模采集时被封禁、被反爬、被诉求，系统不可持续。

---

## 1. 你要的到底是什么（产品形态定义）

### 1.1 Palantir 类系统的本质
Palantir（Foundry/Gotham）的核心不在“写报告”，而在：
1. **Ontology（本体）**：定义对象类型、属性、关系类型、权限与操作。
2. **Objects（对象）**：实体、事件、设施、部队、装备……作为一等公民。
3. **Provenance（溯源）**：对象的每个字段都能追溯数据来源、版本、处理流程。
4. **Actions（动作）**：对对象的修改以动作方式发生，可审计、可回滚、可授权。
5. **Workbench（工作台）**：图谱、时间线、地图、证据查看器、协作、审查。

### 1.2 我们要“超越”的点（AI-native 优势）
在保持上述“对象平台”骨架不变的前提下，AI 可以带来结构性优势：
1. **自动拆解议题（Case → Research Plan）**：自动生成“要验证的断言清单 + 缺口清单 + 采集计划”。
2. **自动闭环补洞（Coverage Loop）**：当覆盖不足/冲突未解释/时间线不一致时，系统自动回到采集与抽取环节补齐。
3. **持续监控（Watchlist/Signals）**：把研究成果转成可监控指标，自动订阅更新并触发再分析。
4. **自我评测与回归（Eval-first）**：每次升级抽取器/本体/提示词，都有离线评测与指标对比，不靠感觉。
5. **开源与可复现**：把“证据包 + 审计回放 + 指标”打包导出，实现第三方复核。

---

## 2. 设计总原则（避免一开始就乱）

下面这些原则不是“建议”，而是“如果不做就一定乱”的硬约束。

### 2.1 Ontology/Object-first（对象优先）
- 系统里流通的主产物不是 markdown，而是：`Entity/Event/Relation/SourceClaim/Assertion`（实体/事件/关系/来源声称/断言）。
- 报告只是其中一种“渲染视图”，可以生成，也可以不生成。

### 2.2 Evidence-first + Archive-first（证据优先 + 先归档再使用）
- 任何进入对象层的 Assertion/Judgment 都必须绑定来源声称 UID（`source_claim_uids[]`），再由 SourceClaim 回溯证据链。
- 任何证据都必须能追溯到 Artifact 快照（网页/PDF 的固化版本），否则视为不合格。
- 证据链必须“钉死版本”：所有引用必须指向 `artifact_version_uid`，禁止对动态内容做“漂浮引用”。

### 2.3 Deterministic IDs（确定性 ID：身份 vs 版本）
OSINT 会被动态网页/A-B/地区化/时间戳打穿；“同 URL = 同内容”是幻觉。正确做法是把 UID 拆成两层：
- `artifact_identity_uid`（身份 UID）：稳定标识“这个来源是谁”（canonical_url + publisher + stable keys）。
- `artifact_version_uid`（版本 UID）：标识“这次采集到的内容是什么”（content_sha256 + fetched_at + renderer_version）。
- `chunk_uid`：基于（artifact_version_uid + anchor_set + quote_hash）可复现生成，确保引用在解析器升级后仍可定位或可回退。
- 任何合并/修订/人工编辑都只能建立在“身份 UID + 版本 UID + 强锚点”上，否则 3 个月必然出现引用漂移与不可复现。

### 2.4 Action-based Mutations（动作式写入）
- 平台里的“修改世界”只能通过 Action（动作）发生：合并实体、修正事件时间、添加关系、标注冲突、批准关键判断。
- Action 必须：校验 → 权限 → 审计 → 可回滚。

### 2.5 Agents 只负责产生“结构化工件”，不得直接落库为事实
- LLM 可以提出候选实体、候选关系、候选断言，但落库必须经过：
  - Schema 校验（Pydantic/JSON Schema）
  - 规则校验（时间窗、字段范围、一致性）
  - 质量闸门（覆盖率、来源多样性、冲突处理）
  - 风险策略（高风险动作走 HITL）

### 2.6 永远把“冲突”当作一等公民
- 冲突不是报告里一句话，而是模型里的显式结构：`assertion.conflicts_with[]`、`evidence.conflict_types[]`。
- 允许存在多套并行解释（竞争性假设），但必须标注证据与不确定性。

---

## 3. 平台的核心对象（数据结构是根）

### 3.1 证据链（你现有项目已经具备骨架）
- ArtifactIdentity：来源身份（canonical_url、publisher、title、first_seen_at...）
- ArtifactVersion：不可变快照（`artifact_version_uid`、`content_sha256`、`fetched_at`、`renderer_version`、`storage_ref(WARC/HTML/PDF/screenshot)`...）
- Chunk：可引用片段（指向 `artifact_version_uid`，含强锚点 `anchor_set`）
- Evidence：证据记录（评分、来源、时效性、冲突标记、license_note、pii_flags）

**强锚点（anchor_set）必须做成“多选择器冗余”，并可健康检查/回退：**
- HTML：`xpath/css_selector` + `TextQuote(前后N字)` + `TextPosition(char_start/char_end)`（至少两种）
- PDF：`page` + `bbox` + `TextQuote`
- 音视频：`timestamp_range` + `transcript_quote`（可选 `frame_hash`）

**锚点健康度（anchor_health）建议做成一等指标：**可稳定定位/是否漂移/是否回退到 quote 搜索；Evidence Vault UI 与 Validator 都要展示。

**关键约束**：报告或判断中出现的任意引用 `[n]` 必须映射到 `Report.references[n] → source_claim_uid → evidence_uid → chunk_uid → artifact_version_uid → artifact_identity_uid`。

### 3.2 实体/事件/关系（对象层的基础）
- Entity：Actor/Organization/Unit/Facility/Equipment/Geography/LegalInstrument/Narrative
- Event：Statement/Diplomatic/Economic/MilitaryPosture/Incident/Exercise/Deployment/Movement/Engagement...
- Relation：BELONGS_TO/LOCATED_AT/OPERATES/ALLIED_WITH/HOSTILE_TO/COOPERATES_WITH/PARTICIPATES_IN/CAUSED_BY/FOLLOWS/RELATED_TO

### 3.3 SourceClaim（来源声称：谁在什么证据里说了什么）
SourceClaim 是平台“可追责语义”的最小单位：尽量贴近来源原句/原段落，并记录说话者、引述链与模态（可能/据称/确认/否认）。

SourceClaim 的最小字段建议：
- `source_claim_uid`
- `case_id`
- `evidence_uid` / `chunk_uid` / `artifact_version_uid`
- `quote`：尽量原文（可多语言）
- `quote_selectors[]`：在 chunk 内的 span selectors（TextQuote/TextPosition）
- `speaker` / `attribution_chain[]`（可选：A 引述 B；二手/三手链）
- `modality`：confirmed/likely/alleged/denied/unknown
- `claim`：结构化槽位（subject/predicate/object/value + time_range），但**不强行融合归一**
- `provenance`：extractor_version、模型、trace_id

### 3.4 Assertion（断言：平台的可计算最小真理单位）
断言是“可被证明或推翻”的可计算原子事实；图谱边、时间线事件、关键判断都从断言聚合而来。

断言的最小字段建议：
- `assertion_uid`
- `case_id`
- `subject`：实体或事件
- `predicate`
- `object/value`
- `time_range`：start/end/approx/raw_text
- `confidence`
- `supporting_source_claim_uids[]`（或关联表 `assertion_source_claims`）
- `conflicts_with[]`
- `provenance`：claim_extractor_version、fuser_version、模型、trace_id

### 3.5 Merge Decision（消歧与融合：平台可用性的分水岭）
- 合并不是“直接改 entity 表”，而是一个可审计决策：
  - winner_entity_uid
  - merged_entity_uids
  - rationale
  - evidence_uids
  - approved_by（auto/hitl/user）

### 3.6 Action（动作：所有写入都必须走它）
最少需要这些动作类型：
1. `merge_entities`
2. `split_entity`
3. `edit_entity_property`
4. `edit_event_time`
5. `add_relation`
6. `resolve_conflict`
7. `approve_key_judgment`
8. `publish_watchlist`

---

## 4. 总体架构（分三大平面）

### 4.1 分层示意
```text
┌─────────────────────────────────────────────────────────────────────┐
│                            Analyst Workbench                         │
│  Evidence | Timeline | Graph | Judgments | Watchlist | HITL | Replay  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────┴─────────────────────────────────────┐
│                         Control Plane (API)                          │
│  Gateway + IAM + Policy + Case/Ontology/Action/Query/Audit/Export     │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ (jobs/events)
┌───────────────────────────────┴─────────────────────────────────────┐
│                       Intelligence/Data Plane                         │
│  LangGraph Orchestrator + Workers                                     │
│  Ingest -> ClaimExtract -> Fuse -> Resolve -> Validate -> Index -> Analyze │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ (tool calls)
┌───────────────────────────────┴─────────────────────────────────────┐
│                          Tool Plane (MCP)                             │
│  MCP Gateway: allowlist/robots/rps/cache/audit + Tool adapters         │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 技术栈建议（可落地、可演进）
- 后端语言：Python（复用现有 `aegi-core` 生态）
- API：FastAPI（同步/异步皆可）
- 编排：LangGraph（有状态、可 checkpoint、可循环）
- 工具：MCP Gateway（统一外联治理与审计）
- 数据（P0）：Postgres（权威源 + FTS + JSONB）+ MinIO（WARC/快照/导出包）+（可选）pgvector
- 派生索引（P1+）：OpenSearch（全文）/ Neo4j（图）/ Qdrant（向量）——全部必须可从 Postgres + MinIO 重建
- 观测：OpenTelemetry + Prometheus/Grafana
- 前端：Next.js（Workbench），图谱 sigma.js，时间线 vis-timeline，地图 MapLibre

---

## 5. “新建项目重来写”怎么做才不丢地基

你担心的“混乱”本质是：目前主线仍是“报告编排”，而不是“对象平台”。

正确做法不是推倒所有代码，而是：
1. 新建一个 **Graph-first 产品主线服务**：建议命名 `aegi-foundry`（或你喜欢的名字）。
2. 把 `aegi-core` 中已经做对的“内核”抽出来复用：
   - evidence schemas + validator（引用闭环）
   - policy/audit/tool runner（可控性与审计）
   - structured generation（结构化输出兜底）
   - prompt isolation（防注入隔离）
   - graph pipeline（抽取雏形）
3. 让 STORM 报告变成一个“渲染插件”，而不是主产品。

工程落地建议：
- P0 不要上来就 20 个微服务。先做 **模块化单体（modular monolith）**：
  - 一个 repo/一个服务进程（API + worker），但模块边界清晰：Case/Ontology/Evidence/Extraction/Resolution/Query。
  - 当吞吐与团队规模上来，再拆分为独立服务。


## 6. 服务与模块划分（职责要清晰，否则一定乱）

> 下面的“服务”可以在 P0 先作为模块存在于同一个进程里，但边界必须明确。

### 6.1 API Gateway / IAM / Policy
**职责**
1. 统一鉴权（API Key/OIDC/JWT）、租户隔离（可选）。
2. 统一限流与 WAF（防滥用、避免被外部探测）。
3. 统一 trace_id 注入与跨服务传播。
4. Policy：模型/工具/预算/导出策略（deny-by-default）。

**关键点**
- Policy 必须覆盖：
  - 模型调用（allowed_models）
  - 工具调用（allowed_tools + 工具风险等级映射）
  - 并发与超时（max_concurrency/timeout_ms）
  - 导出（export 必须显式授权/HITL）

### 6.2 Case Service（案件/事件容器）
**职责**
- 创建/更新/归档 Case（国际事件、议题、冲突、演训、制裁等）。
- 维护 Case 的“研究目标、范围、时间窗、地域、敏感度、约束、当前状态”。

**建议字段**
- `case_id`：对外稳定 ID（建议 ULID）
- `title` / `summary`
- `objective`
- `time_window`（start/end）
- `region`（可多选）
- `sensitivity`（low/medium/high）
- `constraints`（例如：只允许英文来源、只允许官方/智库等）
- `status`（draft/collecting/extracting/resolving/analyzing/published）

### 6.3 Evidence Service（证据链内核）
**职责**
- 管理 ArtifactIdentity/ArtifactVersion/Chunk/Evidence 的全生命周期（身份/版本拆分）。
- 强制 Archive-first 与引用闭环校验（引用必须钉到 `artifact_version_uid`）。
- 强制强锚点协议（anchor_set）+ 锚点健康度检测/漂移回退。
- 证据与合规元数据：license_note、retention_policy、pii_flags、export_restrictions。
- 提供“证据包导出”（manifest + sha256 + anchor_map + ontology_version + trace）。

**你现有项目可直接复用**
- `Artifact/Chunk/Evidence/ReportReference` 等 schema
- 引用闭环 validator
- 审计 ToolTrace/PolicyDecision 的记录方式

### 6.4 Ontology Service（本体与类型系统）
**职责**
- 定义 Object Types / Link Types / Properties / Constraints。
- 版本化管理本体（ontology_version），支持迁移与回滚。
- 兼容性契约：breaking change 检测、deprecate → migrate → remove 流程、case pinning（每个 case 固定 ontology_version）。
- 为 UI 生成表单/字段定义；为抽取器提供 JSON Schema。

**建议实现方式（强烈建议 IaC + 运行时加载）**
- `ontology/` 目录中用 YAML/JSON 定义类型（类似数据库迁移）：
  - object_types/*.yaml
  - link_types/*.yaml
  - property_sets/*.yaml
- Ontology Service 启动时加载并校验，写入 Postgres（版本记录 + hash）。
- 任何变更必须走 Action（需要审查）。
- 建议新增两类接口/产物：
  - `compatibility_report`：变更影响面（删除/改类型/改枚举值等必须阻断或给出迁移）
  - `migration_plan`：backfill/重建策略（含派生索引重建）

### 6.5 Ingestion Service（采集与归档）
**职责**
- 把外部世界治理成 Artifact：搜索、抓取、归档、解析、OCR、翻译、地理解析。
- 统一走 MCP Gateway，禁止业务代码直接外联。
- 维护采集任务队列、重试、去重、缓存命中。

**关键设计**
- Ingestion 的输出不是“文本”，而是：
  - `artifacts[]`（不可变快照）
  - `chunks[]`（带 anchor）
  - `evidence[]`（来源/评分/标签）

### 6.6 Extraction Service（抽取：Chunk → SourceClaim → Assertion）
**职责**
- 从 Chunk 中抽取 Entity/Event/Relation 候选（可选：与 claim 同步产出）。
- 从 Chunk 中抽取 **SourceClaim**（quote + selectors + modality + speaker/attribution）。
- Claim → Assertion 融合（fusion）生成可计算断言，并保留 claim 级别可追责性。
- 生成冲突候选（conflict candidates）。

**关键设计：抽取必须“结构化输出 + 校验兜底”**
- JSON mode / Outlines / post-validate 三段式兜底。
- 每个 extractor 都必须有：
  - 输入 schema
  - 输出 schema
  - 版本号（extractor_version）
  - 评测集（eval）
- 强制两阶段：
  1. Claim extraction 尽量贴原文（不做“归一化改写”）
  2. Assertion fusion 才做融合归一（并输出“为什么这么融合”的结构化 rationale）

### 6.7 Resolution Service（消歧与融合）
**职责**
- 实体消歧（Entity Resolution）：同名不同物、同物不同名。
- 事件去重（Event Deduplication）：同一事件多来源重复报道。
- 合并/拆分都走 Action，必要时 HITL。

### 6.8 Validation / Quality Gate Service（质量闸门）
**职责**
- 引用闭环校验（deterministic）。
- 锚点健康度：anchor 可定位率、漂移率、回退率（quote search）。
- 覆盖率：质量 × 多样性 × 独立互证性（可解释 breakdown），防“转载堆量刷覆盖”。
- Claim→Assertion 约束：每条 Assertion 必须有 ≥N 条独立 SourceClaim 支撑（按策略配置）。
- 时间线一致性校验（规则 + Z3）。
- 抽取质量回归（离线评测对比）。

### 6.9 Index & Query Service（索引与查询）
**职责**
- P0：优先 Postgres FTS/索引 +（可选）pgvector，先把闭环跑通。
- P1+：再引入全文（OpenSearch）/向量（Qdrant）/图（Neo4j）等派生索引加速。
- 提供统一查询 API：
  - Case 概览
  - 图谱邻居/路径
  - 时间线窗口查询
  - 断言检索（predicate/time/confidence）
  - 证据回溯（引用链）

**关键原则**
- Postgres 是权威源；Neo4j/OpenSearch/Qdrant 是可重建的派生索引。

### 6.10 Action Service（动作与协作）
**职责**
- 所有写入与修改通过 Action：
  - 校验（schema + constraints）
  - 权限（RBAC/ABAC）
  - 审计（trace_id + actor）
  - 触发后续重算（re-index / recompute）

### 6.11 Audit/Replay Service（审计回放）
**职责**
- 统一记录：PolicyDecision、ToolTrace、ModelTrace、ActionLog。
- 支持：按 case 回放“当时怎么搜/怎么抓/怎么抽取/为什么合并”。

### 6.12 Export/Publish Service（导出与发布）
**职责**
- 导出视图：
  - 报告（可选）
  - 图谱快照
  - 时间线快照
  - 证据包（manifest + hashes）
- 导出必须先过引用闭环 + HITL（按策略）。

---

## 7. 数据与存储设计（权威源 vs 派生索引）

### 7.1 存储分工（先收敛再扩展）
**P0（闭环优先，小团队可落地）**
1. **Postgres（权威源 + FTS + JSONB + 可选 pgvector）**
   - Case
   - Ontology versions（含 compatibility_report/migration_plan）
   - ArtifactIdentity / ArtifactVersion / Chunk / Evidence（含 anchor_set + anchor_health）
   - SourceClaim（来源声称）
   - Entity/Event/Relation（对象元数据）
   - Assertion（断言：关联 SourceClaim）
   - MergeDecision
   - ActionLog + Review/HITL
   - Audit records（PolicyDecision/ToolTrace/ModelTrace）

2. **MinIO（不可变对象存储）**
   - ArtifactVersion 原文快照（WARC/HTML/PDF/图片/视频元数据/截图）
   - 导出：报告/证据包（manifest + hashes + anchor_map）

**P1+（规模化后再拆索引，全部可重建）**
3. **OpenSearch（全文派生索引）**
   - Artifact/Chunk/Evidence 文本索引
   - Entity/Event/SourceClaim/Assertion 的可检索字段

4. **Qdrant（向量派生索引）**
   - Chunk embeddings（语义检索与候选生成）
   - SourceClaim/Assertion embeddings（相似 claim/断言检索）
   - Entity profile embeddings（消歧候选）

5. **Neo4j（图查询派生索引）**
   - Entity/Event 节点
   - Relation 边
   - 可选：把 Assertion 映射为边属性或独立节点（建议先边属性，后独立节点）

### 7.2 关键表（建议最小集合）
> 这里只给“必须有”的表。非关键字段（如 created_by）按需要补。

1. `cases`
2. `ontology_versions`
3. `artifact_identities`
4. `artifact_versions`
5. `chunks`
6. `evidence`
7. `source_claims`
8. `entities`
9. `events`
10. `relations`（可选：如果 Postgres 也存关系权威源）
11. `assertions`
12. `assertion_source_claims`（关联表）
13. `assertion_conflicts`
14. `merge_decisions`
15. `actions`
16. `action_events`（动作事件流，便于重放与异步处理）
17. `reviews`（HITL）
18. `audit_policy_decisions` / `audit_tool_traces` / `audit_model_traces`

### 7.3 断言表设计要点（避免后期灾难）
- `predicate` 不是随便字符串：必须来自 Ontology 的枚举或注册表。
- `subject_kind/subject_uid` + `object_kind/object_uid` 支持 Entity/Event/Value。
- `time_start/time_end/is_approx/raw_text` 必须能表达“不确定时间”。
- 断言与证据不要直接硬绑数组：建议 `assertion_source_claims` 作为主关联（Evidence 可由 claim 回溯并可缓存）。
- `artifact_identity_uid` 与 `artifact_version_uid` 必须拆开，否则版本变化/重复抓取会把引用闭环搞死。

---

## 8. MCP 工具平面（Tool Plane）设计（无限搜索 ≠ 无治理）

### 8.1 为什么 MCP 是必须的
- MCP 的价值不是“能调用工具”，而是把外联治理集中化：
  - 域名 allow/deny
  - robots/ToS 记录
  - per-domain RPS 与并发
  - 缓存
  - 审计
  - 输出 schema 规范化

### 8.2 工具分类与最小工具集
**Acquisition（采集）**
1. `meta_search`：元搜索（SearxNG/Serper/Bing 等适配）
2. `web_fetch`：单页抓取（轻量）
3. `web_crawl`：多页抓取（深度/分页）
4. `archive_url`：归档固化（ArchiveBox/自研存档）
5. `rss_pull`：RSS 拉取（可选）

**Processing（处理）**
1. `doc_parse`：文档解析（Unstructured/Tika/GROBID）
2. `ocr`：图片/PDF 扫描 OCR
3. `lang_detect`
4. `translate`
5. `geocode`

**Internal（内生）**
1. `graph_query`
2. `vector_query`
3. `assertion_search`

### 8.3 工具输出必须“净化 + 白名单字段”
- 外部内容永远只进入 evidence zone。
- 工具返回中“疑似提示注入字段”必须标记并禁止进入 system 指令。

### 8.4 工具安全（必须当成一级产品能力）
- 强认证：每个 tool server、每个用户、每个 case 的令牌隔离（case-scoped token）。
- 细粒度授权：tool × domain × action × budget（默认拒绝，显式放行）。
- 工具输入/输出净化：字段白名单 + 可疑注入标记 + 结构化 schema 校验。
- 可重放 transcript：ToolTrace 必须可回放，但要脱敏/加密/访问控制（防数据外泄与越权扩散）。

---

## 9. LangGraph 编排（把“研究”变成可回放状态机）

> 关键点：不要让系统退化成“聊天式自由发挥”。
> 
> 我们用 LangGraph 做有状态编排：每一步都产出结构化工件，并写入存储；支持 checkpoint、重跑、HITL 中断。

### 9.1 统一状态与工件（Artifacts of Work）
每个 Case 研究流程会产出一组“工件”（不是 MinIO Artifact，而是工作产物）：
- `ResearchPlan`：研究计划（结构化）
- `QuerySet`：查询集合（按 facet/章节）
- `IngestionRun`：采集运行记录（统计、失败、命中缓存等）
- `ExtractionRun`：抽取运行记录（抽取器版本、覆盖率、冲突数）
- `ResolutionRun`：消歧融合记录（候选数、自动合并数、HITL 数）
- `AnalysisPackage`：分析包（Key Judgments/Scenarios/Watchlist）

这些工件都要落库，并可在 UI 中查看“版本历史”。

### 9.2 Graph 1：CaseBootstrapGraph（从事件种子到研究计划）
**输入**：用户一句话（或一段）事件描述

**输出**：
- Case（创建）
- ResearchPlan（结构化）
- 初始 QuerySet（结构化）
- 预算与策略（Policy + Budget）

**核心节点**
1. `NormalizeSeed`
   - 清洗用户输入、抽取时间窗/地域/关键词
2. `Planner.GenerateResearchPlan`
   - 生成“要验证的断言清单 + 缺口清单 + facet 划分 + 风险点”
   - 输出必须是 JSON，严格 schema 校验
3. `Planner.GenerateInitialQueries`
   - 每个 facet 2-4 条检索式（含时间范围、优先来源类型）
4. `Policy.InitBudget`
   - 设置 tokens/tool_calls/deadline 等预算
5. `Case.Create`

**ResearchPlan（示例字段）**
- `facets[]`: 
  - `facet_id`, `title`, `questions[]`, `required_source_types[]`, `depth_policy`
- `must_verify_assertions[]`（候选断言）
- `known_unknowns[]`
- `priority_signals[]`（观察信号）

### 9.3 Graph 2：IngestionGraph（采集闭环：覆盖不足就回环）
**目标**：把互联网变成可审计证据链。

**输入**：QuerySet + Policy/Budget + Domain policy

**输出**：Artifacts/Chunks/Evidence + IngestionRun

**核心节点（强制 Archive-first）**
1. `Search(meta_search)`
2. `SelectURLs`
   - 规则：域名策略、去重、评分、时间范围优先
3. `Archive(archive_url)`
4. `Fetch/Crawl(web_fetch/web_crawl)`
5. `Parse(doc_parse + ocr + lang_detect + translate)`
6. `Chunk`
7. `EvidenceCreate`
8. `CoverageCheck`
   - 若 coverage < 阈值：生成 GapQuery → 回到 Search

**CoverageCheck 必须可解释、可抗“刷覆盖”**
- Coverage 不是“≥N 条 evidence”这种幼稚指标，而应输出 score breakdown：
  - 质量（source reliability / info credibility）
  - 多样性（不同 publisher/source_type/语言/地区；转载/镜像不计数）
  - 独立互证性（关键字段在独立 SourceClaim 间一致；冲突必须显式呈现或解释）
  - 时效性（与 case 时间窗匹配）
- 不达标时生成 GapQuery：系统要知道“缺什么”（缺官方/缺一手/缺地理证据/缺时间窗等），而不是只知道“没过”。

### 9.4 Graph 3：ExtractionGraph（抽取 → SourceClaim → 断言融合 → 冲突候选）
**输入**：chunks + evidence + ontology_version

**输出**：entities/events/relations/source_claims/assertions + ExtractionRun

**核心节点**
1. `Extractor.EntitiesEventsRelations`
   - 从 chunk 抽取实体/事件/关系
   - 输出 schema：EntityExtractionResult / EventExtractionResult / RelationExtractionResult
2. `Extractor.SourceClaimExtract`
   - 从 chunk 抽取 SourceClaim（quote + selectors + speaker/attribution + modality + claim slots）
   - 输出必须结构化，并保留“来源怎么说”的原句/原段落
3. `Normalizer.TimeGeo`
   - 时间归一：相对时间 → 绝对时间（带 approx/raw_text）
   - 地理归一：地名 → geo_point/bbox（允许缺失）
   - 注意：归一的是 claim slots，不改写 quote
4. `AssertionFusion`
   - 对 SourceClaim 做聚类/归一/融合，生成 Assertion（可计算），并输出结构化 rationale
5. `ConflictDetector`
   - claim-level：同 subject+predicate 在同时间窗出现互斥值 → 冲突候选
   - assertion-level：融合后仍互斥/不可同时为真 → 断言冲突
6. `Persist`
   - Postgres 写入权威源
   - 触发 Neo4j/OpenSearch/Qdrant 增量更新或标记待重建

### 9.5 Graph 4：ResolutionAndAnalysisGraph（消歧 → 时间线 → 判断）
**输入**：assertions + entities/events + existing graph

**输出**：
- merge decisions
- resolved graph/timeline
- analysis package（judgments/scenarios/watchlist）

**核心节点**
1. `EntityResolution.GenerateCandidates`
   - 候选生成：
     - 词法（name/alias）
     - 向量相似（profile embedding）
     - 同一上下文共现（co-occur）
     - 地理/时间一致性
2. `EntityResolution.PairwiseScoring`
   - 规则特征 +（可选）LLM 判别（仅对高价值候选）
3. `EntityResolution.ClusterAndProposeMerges`
   - 输出 MergeProposal（结构化）
4. `HITL.MergeApproval`（按风险策略）
5. `TimelineBuilder`
   - 事件排序、窗口聚合、同事件多来源合并
6. `ConstraintValidation`
   - Z3/规则检查：时间窗矛盾、因果顺序矛盾、互斥资源冲突
7. `Analyst.KeyJudgments`
   - 输出结构化 judgments：事实/推断/假设
8. `RedTeam.Critic`
   - 竞争性解释、缺口清单、反证建议
9. `WatchlistBuilder`

### 9.6 Graph 5：MonitoringGraph（持续监控与再分析）
**输入**：watchlist + subscriptions

**输出**：alerts + incremental ingestion/extraction

关键：监控必须可配置、可暂停、可审计；避免变成“无限爬虫”。

---

## 10. 多智能体体系（多智能体 ≠ 多嘴）

> 多智能体的正确打开方式：分工明确、输入输出结构化、互相审查、自动补洞。

### 10.1 角色划分（建议最小集合）
1. **Planner Agent（战略规划器）**
   - 输入：事件种子
   - 输出：ResearchPlan（facet/问题/断言/缺口/风险）

2. **Source Strategist（检索策略）**
   - 输入：facet/questions
   - 输出：QuerySet（含时间范围、优先来源类型、优先域名建议）

3. **Collector（采集执行）**
   - 输入：QuerySet
   - 输出：Artifact/Chunk/Evidence（Archive-first）

4. **Extractor（结构化抽取）**
   - 输入：chunks + ontology
   - 输出：SourceClaims + Entity/Event/Relation + Assertions

5. **Resolver（消歧融合）**
   - 输入：entities/assertions
   - 输出：MergeProposals + resolved mappings

6. **Timeline Builder（时间线构建）**
   - 输入：events/assertions
   - 输出：TimelineItems（结构化）

7. **Intel Analyst（情报分析）**
   - 输入：resolved assertions + conflicts + gaps
   - 输出：KeyJudgments（结构化）

8. **Red Team Critic（红队审查）**
   - 输入：judgments + evidence coverage
   - 输出：challenge list + counter-hypotheses + required evidence

9. **Watchlist/Signals（观察指标）**
   - 输入：judgments/gaps
   - 输出：watchlist items + triggers + subscriptions

### 10.2 CrewAI 的正确使用位置（可选）
- CrewAI 适合做“分析委员会”：Analyst + RedTeam + Editor 的对抗讨论。
- CrewAI 不适合做“写库动作”：合并/修正时间线/标注冲突必须走 Action + 校验。

### 10.3 提示词体系（Prompt Profiles）
每个 Agent 必须有明确 profile（system 指令）与输出 schema。

**硬规则（必须写进 system）**
1. 只基于证据，不得编造。
2. 输出必须是 JSON，严格符合 schema。
3. 任何结论必须列出 supporting_source_claim_uids（必要时同时给 supporting_evidence_uids）。
4. 如证据不足，必须输出 gaps。

---

## 11. 实体消歧与融合（Entity Resolution/Fusion）

> 这是 Palantir 体验的分水岭：
> - 没有消歧融合：图谱会变成“同一国家 10 个节点、同一组织 5 个名字”，不可用。
> - 只有 LLM 消歧：不可复现、不可解释、成本爆炸。
> 
> 正确做法：**规则/统计/向量/LLM 混合**，并把合并决策作为可审计对象。

### 11.1 分层策略（从便宜到昂贵）
1. **Blocking/候选生成（便宜）**
   - 词法：name/alias 规范化（大小写、去标点、转写）
   - 同一国家/地理范围限制
   - 同一实体类型限制（Unit 不和 Equipment 直接比）
   - 向量近邻：用 embeddings 找 TopK 候选

2. **Pairwise Scoring/对比打分（中等成本）**
   - 特征：
     - 名称相似（Jaro-Winkler/Levenshtein）
     - 别名重叠
     - 位置一致（geo distance）
     - 时间一致（活动时间窗）
     - 上下文共现（同一事件/同一关系邻居）
     - 来源一致（同一官方机构页面）
   - 产出：match_score（0-1）+ rationale（结构化）

3. **LLM 判别（高成本，仅用于边界样本）**
   - 只对“高价值且高不确定”的候选调用 LLM
   - 输出必须结构化：same/different/unknown + reasons + required evidence

4. **Clustering/聚类（可复现）**
   - Union-Find 或层次聚类
   - 形成 merge clusters（候选合并簇）

5. **Merge Action（写入）**
   - 自动合并仅限 low-risk；高风险进入 HITL 队列

### 11.2 风险分级与 HITL 触发
建议把合并动作分 3 档：
1. **Auto-merge（低风险）**
   - score ≥ 0.95
   - 证据来源 ≥ N
   - 无冲突断言

2. **Suggest-only（中风险）**
   - 0.80 ≤ score < 0.95
   - 进入“候选合并”列表，等待人工确认

3. **Block（高风险）**
   - score < 0.80 或涉及高敏对象（军队单位/设施/装备）
   - 必须 HITL

### 11.3 合并后的引用一致性（必须解决的工程细节）
- 一旦实体合并：
  - 旧 entity_uid 不能直接消失：必须保留 redirect/alias 映射
  - 所有关联 assertion/relations/events 需要“重映射”或在查询层动态解析
- 建议采用：
  - `entity_redirects(old_uid -> new_uid)`
  - Query 层对 old_uid 自动 resolve 到 new_uid

### 11.4 事件去重（Event Dedup）
- 同一事件在多来源重复报道：
  - 时间窗重叠
  - 地点接近
  - 参与方高度重叠
  - 摘要语义相近
- 事件去重也要产出“合并决策”，并保留来源证据。

---

## 12. 冲突与一致性（让系统“可计算”，而不是“口头解释”）

### 12.1 冲突是什么
冲突不是“观点不同”这么简单，而是：
- 同一 subject/predicate 在同一时间窗出现互斥 object/value
- 或同一事件的关键字段（时间/地点/参与方）在不同来源间不可同时为真

### 12.2 冲突类型（建议最小枚举）
1. `timeline`：时间矛盾（先后顺序、时间窗）
2. `location`：地点矛盾（相距过远且同一时间）
3. `participant`：参与方矛盾（是否参与、角色冲突）
4. `capability`：能力/装备参数矛盾
5. `attribution`：归因矛盾（谁做的）
6. `causality`：因果矛盾

### 12.3 冲突数据结构（建议）
- `assertion_conflicts(asn_a, asn_b, conflict_type, severity, notes)`
- UI 必须能一键打开冲突两侧证据片段并对比。

### 12.4 时间线一致性（Z3/规则）
**为什么要做**：时间线是态势研判的骨架；只要时间线乱，后面全乱。

**最小约束集合**
1. `event.time_end >= event.time_start`
2. `FOLLOWS` 边必须满足时间顺序
3. 同一实体在同一时间窗不能同时出现在相距极远的地点（可配置阈值）
4. 关键事件必须落在 Case 的 time_window 内（或标记 out_of_scope）

**实现建议**
- P0：规则校验 + 报警
- P1：引入 Z3 建模关键约束，输出可解释冲突（哪个约束被违反）

---

## 13. 分析层（Key Judgments / 情景推演 / Watchlist）

> 目标：让“分析”变成结构化对象，而不是散文。
> 
> 你不想要“乱七八糟的报告”，那我们就把报告降级为导出视图，把分析结果固定为可计算对象。

### 13.1 Key Judgment（关键判断）
**关键判断不是一句话**，而是一个可审计对象：

建议最小 schema：
- `judgment_uid`
- `case_id`
- `title`（一句话）
- `judgment_type`：`FACT | INFERENCE | HYPOTHESIS`
- `confidence`：0-1
- `supporting_assertion_uids[]`
- `supporting_source_claim_uids[]`
- `supporting_evidence_uids[]`
- `counter_assertion_uids[]`（反证/冲突）
- `counter_source_claim_uids[]`
- `gaps[]`（缺口：缺什么来源/时间段/参与方）
- `implications[]`（影响：仅分析，不做作战指令）
- `updated_at` + `version`

**硬性规则**
1. FACT 必须能回溯到明确 SourceClaim（含 quote_selectors）并定位到证据片段；若无法做到，必须降级为 INFERENCE。
2. INFERENCE 必须写清楚“推断链条”与不确定性。
3. HYPOTHESIS 必须列出触发条件与可证伪证据。

### 13.2 Scenarios（情景推演/分支）
情景不是“预测”，而是结构化的分支树：
- `scenario_uid`
- `name`
- `assumptions[]`（断言引用）
- `branches[]`：每个分支包含 triggers、signals、expected_events、risks

**关键原则**
- 情景的所有假设必须引用断言/证据。
- 不输出可执行作战方案，只输出“可能演化路径 + 触发条件 + 风险”。

### 13.3 Watchlist（观察指标/信号）
Watchlist 必须可操作、可订阅、可触发再分析。

建议最小 schema：
- `watch_uid`
- `case_id`
- `category`：entity_change/event_trigger/metric_threshold/timeline_milestone/uncertainty
- `indicator`：一句话可监控指标
- `trigger_conditions[]`：结构化触发条件
- `linked_entity_uids[]`
- `linked_event_uids[]`
- `source_claim_uids[]`（可选：把 watch 直接钉到 claims）
- `evidence_uids[]`
- `priority`：high/medium/low
- `subscription`：数据源/频率/工具

**触发后的动作**
- 触发 → 生成增量 QuerySet → 进入 MonitoringGraph → 更新断言与判断版本

### 13.4 Analysis Package（分析包：给工作台渲染的统一输入）
为了让 UI 渲染稳定，建议把“当前版本的分析结果”打包：
- `analysis_package_uid`
- `case_id`
- `judgments[]`
- `scenarios[]`
- `watchlist[]`
- `quality_summary`：覆盖率、来源多样性、冲突数、时间线一致性得分
- `build_info`：模型/抽取器版本/时间戳

---

## 14. 查询与 API 设计（UI 不应该自己拼逻辑）

> Workbench 的核心体验来自“查询 API 设计”。
> 你不能让前端去 join 一堆表再算图谱与时间线，否则迭代必崩。

### 14.1 API 分组
1. Case
2. Ontology
3. Evidence
4. Objects（Entity/Event/Relation/SourceClaim/Assertion）
5. Graph
6. Timeline
7. Actions + Reviews
8. Analysis Package
9. Export
10. Audit/Replay

### 14.2 必备端点（示例）
**Case**
- `POST /cases` 创建 case
- `GET /cases/{case_id}`
- `GET /cases/{case_id}/status`

**Ingestion / Runs**
- `POST /cases/{case_id}/runs/ingest` 启动采集
- `GET /cases/{case_id}/runs/ingest/{run_id}`

**Extraction / Resolution**
- `POST /cases/{case_id}/runs/extract`
- `POST /cases/{case_id}/runs/resolve`

**Evidence**
- `GET /cases/{case_id}/evidence`（分页、过滤 domain/time/tag）
- `GET /evidence/{evidence_uid}`（返回 chunk + artifact_version + anchor_set + anchor_health）
- `GET /artifacts/{artifact_identity_uid}`（返回 identity 元信息 + versions 列表）
- `GET /artifact_versions/{artifact_version_uid}`（返回版本元信息 + storage_ref + content_sha256）

**Objects**
- `GET /cases/{case_id}/entities` / `GET /entities/{uid}`
- `GET /cases/{case_id}/events` / `GET /events/{uid}`
- `GET /cases/{case_id}/source_claims`（按 predicate/modality/speaker/evidence_uid 过滤）
- `GET /source_claims/{uid}`（返回 quote + selectors + 证据链）
- `GET /cases/{case_id}/assertions`（predicate/time/confidence 过滤）
- `GET /assertions/{uid}`（返回 assertion + supporting/counter claims）

**Graph**
- `GET /cases/{case_id}/graph/summary`（节点数、边数、类型分布）
- `GET /graph/entities/{uid}/neighbors?types=...&limit=...`
- `GET /graph/path?source=...&target=...&max_depth=...`

**Timeline**
- `GET /cases/{case_id}/timeline?start=...&end=...&types=...`
- `GET /timeline/events/{event_uid}`（返回 event + assertions + evidence）

**Actions/HITL**
- `POST /actions`（提交动作：merge/edit/add_relation）
- `GET /actions/{action_uid}`
- `POST /reviews/{review_id}/approve|reject`

**Analysis**
- `GET /cases/{case_id}/analysis/latest`
- `POST /cases/{case_id}/analysis/rebuild`

**Audit/Replay**
- `GET /cases/{case_id}/audit/tool_traces`
- `GET /cases/{case_id}/replay/{trace_id}`

### 14.3 GraphQL vs REST
- P0 建议 REST（更直接），GraphQL 可在 P1 引入用于 Workbench 组合查询。

---

## 15. Workbench（工作台 UI）设计（这才是“像 Palantir”）

> 关键点：UI 必须围绕对象与证据工作，而不是围绕“文章”。

### 15.1 Case 首页（总览）
**左侧：Case 元信息**
- 标题、时间窗、地域、敏感度
- 当前版本：analysis_package_uid
- 质量摘要：coverage、source diversity、conflicts、timeline consistency

**右侧：五个入口**
1. Evidence Vault
2. Timeline
3. Graph
4. Key Judgments
5. Watchlist

### 15.2 Evidence Vault（证据库）
**核心交互**
- 过滤：domain、时间范围、语言、标签、可信度、工具来源
- 列表项展示：标题/来源/时间/score/是否冲突
- 点击进入证据详情：
  - Chunk 高亮（按 anchor_set）
  - Artifact 快照预览（HTML/PDF）
  - “引用链”展示：Evidence→Chunk→ArtifactVersion→ArtifactIdentity（含 anchor_health）
  - 本 chunk 抽取的 SourceClaims（quote + modality + speaker）
  - 相关断言/相关实体/相关事件

**必须功能**
- 对比模式：并排比较两条冲突证据
- 固化证明：显示 content_sha256 + fetched_at + trace_id
- 锚点健康度：可定位/漂移/回退（quote search），并提示“本引用是否仍稳”

### 15.3 Timeline（时间线）
**时间线不是装饰，而是态势骨架**

**核心交互**
- 缩放（小时/天/周/月）
- 分组（按事件类型、参与方、地域）
- 时间窗过滤（滑块）
- 冲突提示（颜色/图标）：时间矛盾、归因矛盾

**事件详情侧栏**
- 事件摘要 + 置信度
- 参与方（entities）
- 支撑断言列表（assertions）
- 支撑证据列表（evidence）
- 冲突断言（conflicts）
- “修正时间/合并事件/拆分事件”动作入口（Action）

### 15.4 Graph（关系图谱）
**核心交互**
- 过滤：节点类型、边类型、置信度阈值、时间窗
- 邻居展开：点击实体 → neighbors
- 路径查询：source→target（用于“关系链”展示）
- 社区/聚类视图（可选 GraphRAG 社区摘要）

**实体详情侧栏**
- 基本属性、别名
- 相关断言（按 predicate 分类）
- 断言 → SourceClaim 对照（先展示“各来源怎么说”，再展示融合断言）
- 相关事件（时间线窗口）
- 支撑证据
- 合并建议（Merge proposals）

### 15.5 Key Judgments（关键判断）
**展示规则**
- 默认按“判断类型（FACT/INFERENCE/HYPOTHESIS）”分区
- 每条 judgment 展示：
  - confidence
  - supporting source_claim count（独立来源数）
  - supporting evidence count
  - source diversity
  - gaps count
  - conflicts indicator

**审查与协作**
- Red Team 面板：对每条 judgment 给出挑战点
- 允许用户标注：接受/拒绝/需要更多证据

### 15.6 Watchlist（观察指标）
**核心交互**
- 列表：priority、触发条件、关联实体/事件
- 订阅设置：数据源、频率、触发动作
- 告警记录：何时触发、触发后更新了哪些断言/判断

### 15.7 Replay（审计回放）
> 这是“可复核/可回放”差异化能力的关键 UI。

- 以时间轴回放：
  - 当时搜了什么 query
  - 返回了哪些结果
  - 抓取/归档了哪些 URL
  - 解析得到哪些 chunks
  - 抽取器产出了哪些实体/SourceClaims/断言
  - 哪个 Action 导致合并

---

## 16. 安全与治理（没有治理就没有平台）

### 16.1 外联治理（Scrape Guard）
必须集中在 MCP Gateway：
- domain allowlist（默认拒绝）
- denylist（高封禁/高风险站点）
- robots require allow
- per-domain rps + concurrency
- cache ttl
- max content bytes
- allowed mime types

### 16.2 提示注入防护（Prompt Injection）
硬性工程措施：
1. 外部内容只能进入 evidence zone
2. system 指令只能来自 internal
3. 工具输出必须净化（字段白名单）
4. 对证据内容做最小转义，避免破坏边界

### 16.3 数据权限（RBAC/ABAC）
- Case 级别权限：谁能看/改/导出
- Action 级别权限：谁能合并实体、谁能批准导出
- 数据源级别权限：某些来源可能受许可限制（license_note）

### 16.4 合规（版权/许可/隐私）
- Retention：按 case/来源配置保留期；到期自动清理 Evidence/导出包（满足合规与成本控制）。
- PII：进入对象层前做 PII 探测与最小化；导出默认脱敏；支持删除/更正请求与审计记录。
- Copyright/License：归档与导出按许可策略执行；对受限来源只允许保存最小必要引用片段/元数据，并在 Evidence/Export 中保留 license_note 与限制。

### 16.5 供应链与运行安全
- 解析器（doc_parse/ocr）必须沙箱化（防恶意文件）
- 限制文件类型与大小
- 工具执行超时与资源限制

---

## 17. 运维与可观测性（让系统能长期跑）

### 17.1 可观测性
- Trace：OpenTelemetry，跨服务传播 trace_id
- Metrics：
  - 工具成功率/封禁率/缓存命中
  - 抽取耗时/失败率
  - 断言数、冲突数、覆盖率
  - entity resolution 候选规模与 HITL 比例
- Logs：结构化日志，按 case_id/trace_id 可检索

### 17.2 后台作业与重建
- 索引可重建：Neo4j/OpenSearch/Qdrant 都可以从 Postgres + MinIO 重建
- 提供“重建按钮/接口”：
  - rebuild_graph_index
  - rebuild_search_index
  - rebuild_vector_index

### 17.3 成本控制
- BudgetTracker：token/tool_calls/deadline
- 动态深度控制：coverage 达标就停止，不做无意义的无限爬
- 分模型路由：规划/抽取/写作用不同模型（性价比）

---

## 18. 评测与质量闸门（想超越，就必须可量化）

### 18.1 指标体系（建议）
1. **抽取质量**
   - entity/event precision/recall/f1
   - relation accuracy
   - source_claim extraction accuracy（slots/modality/speaker/attribution）
   - geolocation match rate

2. **证据质量**
   - anchor_locate_rate（锚点可定位率）/ drift_rate（漂移率）
   - citation hit rate（引用命中率）
   - source diversity（来源多样性）
   - conflict coverage（冲突显式呈现覆盖率）
   - claim_grounding_rate（Assertion 是否可回溯到足够独立 SourceClaims）

3. **一致性**
   - timeline consistency（时间线一致性）
   - fact consistency（事实一致性）

4. **消歧质量**
   - merge precision（合并正确率）
   - hitl rate（人工介入比例）

5. **运维指标**
   - crawl success/block/cache hit
   - latency
   - cost

### 18.2 质量闸门（Gate）建议阈值（可配置）
- coverage_score ≥ 0.7
- source_diversity ≥ 3
- citation_hit_rate ≥ 0.95
- anchor_locate_rate ≥ 0.98
- claim_grounding_rate ≥ 0.95
- timeline_consistency ≥ 0.9
- 关键判断中 FACT 占比（可选）

不达标策略：
1. 自动补洞循环（回到 IngestionGraph）
2. 或降级输出（明确“证据不足/无法判断”）
3. 或触发 HITL

---

## 19. 路线图（从可用到卓越）

### Phase 0（2-4 周）：对象闭环 MVP
- Case + Evidence Vault + Timeline + Graph 的最小可用闭环
- Archive-first 工具链可用
- 身份/版本 UID + 强锚点协议（artifact_identity/version + anchor_set + health）
- 抽取 → SourceClaim → Assertion 融合（两阶段）
- 基础查询 API

### Phase 1（4-8 周）：消歧融合 + 质量闸门
- Entity Resolution（候选 + 合并动作 + HITL）
- 冲突结构化呈现 + 冲突 UI 对比
- 时间线一致性校验
- 评测回归套件

### Phase 2（8-12 周）：持续监控与自动再分析
- Watchlist + MonitoringGraph
- 订阅与告警
- 增量更新与版本化分析包

### Phase 3（12+ 周）：协作、规模化与高级分析
- 多人协作与权限
- 情景推演模块化（Scenarios）
- 图谱社区摘要与检索增强（GraphRAG）
- 数据治理体系（OpenMetadata + GX + Airflow/Kafka）

---

## 20. 与现有 aegi-core 的关系（怎么复用，怎么“干净重来”）

你完全可以新建项目“干净重来”，但建议把 `aegi-core` 当作内核参考与复用来源：

**建议直接复用/迁移的模块**
1. 证据链 schema（Artifact/Chunk/Evidence/ReportReference）
2. 引用闭环校验（EvidenceValidator）
3. 策略引擎（PolicyEngine）
4. 工具运行器（ToolRunner：策略/审计/并发/净化）
5. 结构化生成器（StructuredGenerator：JSON mode/outlines/post-validate）
6. PromptBuilder（system/user/evidence 区隔离）
7. GraphRAG 抽取雏形（可作为起点）

**建议在新项目里“重新定义主线”的部分**
1. 把 STORM（报告编排）降级为可选导出器
2. 以 Assertion/Action/Ontology 为核心重建平台 API 与 UI

---

## 21. 开源组件选型（什么值得用，什么别碰）

> 你的问题非常关键：不是“把开源项目堆一起”，而是“把它们放在正确的层”。

### 21.1 编排与多智能体
1. **LangGraph（主编排）**
   - 价值：有状态、可 checkpoint、支持循环、支持 HITL interrupt
   - 适用：研究流水线状态机（Plan→Collect→Extract→Resolve→Analyze）

2. **CrewAI（分析委员会，可选）**
   - 价值：多角色对抗讨论，适合红队审查、竞争性解释
   - 不适用：数据平面（采集/落库/合并），否则不可控不可回放

### 21.2 工具与外联治理
1. **MCP（必须）**
   - 价值：工具接入标准化 + 可治理外联
   - 你现有 `aegi-mcp-gateway` 已经走在正确方向：工具注册表、Scrape Guard

2. **搜索：SearxNG / Serper / Bing 等**
   - 建议：先用 SearxNG 做元搜索，接口稳定后再扩展

3. **抓取：Playwright/自研抓取器（可选）**
   - 关键：抓取一定要受域名策略与并发限制

4. **归档：ArchiveBox / WARC**
   - Archive-first 的核心是“固化版本”，否则证据不可复核

5. **解析：Unstructured / Apache Tika / GROBID**
   - Unstructured 适合通用文档；学术/报告可考虑 GROBID

### 21.3 索引与存储
1. **Postgres（权威源）**
2. **MinIO（对象存储）**
3. **OpenSearch（全文）**
4. **Qdrant/Milvus（向量）**
5. **Neo4j（图）**
6. **GraphRAG（方法论/管线）**
   - Microsoft GraphRAG 更像“知识图谱+摘要检索增强管线”的参考实现

### 21.4 数据治理与质量
1. **Great Expectations（质量闸门）**
2. **OpenMetadata / DataHub（元数据与血缘，可选）**
3. **Airflow / Temporal（调度，可选）**

### 21.5 实体消歧开源库（建议引入）
- **Splink**：大规模 record linkage（SQL 驱动）
- **dedupe**：Python 侧 record linkage
- **recordlinkage**：特征工程与匹配

我们可以把这些作为“候选生成与打分器”，再叠加 LLM 处理边界样本。

### 21.6 你目录里的参考项目怎么用（`开源项目参考/`）
1. `开源项目参考/searxng`
   - 适用：元搜索入口（工具平面），输出可审计、可回放。
2. `开源项目参考/archivebox`
   - 适用：Archive-first 归档固化（WARC/多格式产物），为 Evidence/引用提供“版本锚”。
3. `开源项目参考/unstructured` + `开源项目参考/tika`
   - 适用：文档解析与结构化抽取（Chunk/SourceClaim 上游），用于 PDF/网页/Office。
4. `开源项目参考/spiderfoot`
   - 适用：OSINT 模块化与 correlations 规则范式；用于“质量闸门/可解释信号”。
5. `开源项目参考/intelowl` / `开源项目参考/cortex`
   - 适用：Analyzer/Plugin 体系；建议以外部服务方式接入（MCP 调用），输出落 Evidence zone。
6. `开源项目参考/intelmq`
   - 适用：数据合同（Report/Event）与管线化；用于规范工具输出 schema。
7. `开源项目参考/misp` / `开源项目参考/opencti`
   - 适用：互操作目标与对象化参照系；优先做 import/export 映射（MISP/STIX）。
8. `开源项目参考/timesketch` / `开源项目参考/dfir-iris-web`
   - 适用：协作工作台、时间线视图、worker 模式与分层架构参考。
9. `开源项目参考/thehive`
   - 适用：历史语义参考（Case/Task/Observable）；不要作为核心依赖。

---

## 22. 让它“超过 Palantir”的关键增量（不是口号）

如果只是做 Palantir 的开源仿制品，很难超过。要“超越”，必须发挥 AI-native 与开源的组合优势：

1. **Auto-coverage loop（自动补洞闭环）**
   - 任何 coverage 不达标、冲突未解释、时间线矛盾 → 自动回到采集与抽取

2. **Evidence Package（证据包）标准化**
   - 一键导出：manifest + sha256 + anchor_map + ontology_version + claim_map +（脱敏）trace + 引用映射
   - 第三方能复跑与复核（开源社区可参与）

3. **Eval-first（评测驱动开发）**
   - 每个 extractor/skill 都必须带评测集与指标
   - 任何升级必须通过回归

4. **Open Skill Ecosystem（技能生态）**
   - 让领域专家用“技能包”扩展平台：
     - 新本体字段
     - 新抽取器
     - 新质量闸门
     - 新视图组件

5. **Cross-lingual OSINT（跨语言融合）**
   - 自动翻译 + 跨语言实体链接
   - 把同一事件的多语报道融合为一套断言与冲突结构

6. **Human-in-the-loop 的工程化（不是手工）**
   - HITL 只出现在“高风险动作”上：合并、导出、关键判断批准
   - UI 提供一键对比证据与撤销

---

## 23. 附录：关键结构化输出（示例）

### 23.1 ResearchPlan（Planner 输出）
```json
{
  "plan_uid": "plan_...",
  "case_id": "case_...",
  "facets": [
    {
      "facet_id": "f_background",
      "title": "Background & Drivers",
      "questions": ["What happened?", "What changed recently?"],
      "required_source_types": ["official", "thinktank", "news"],
      "depth_policy": {"min_sources": 5, "max_iterations": 2}
    }
  ],
  "must_verify_assertions": [
    {"subject": "...", "predicate": "...", "object": "...", "time_range": "..."}
  ],
  "known_unknowns": ["Exact unit identity", "Precise timeline"],
  "priority_signals": ["New exercise notice", "Satellite imagery update"]
}
```

### 23.2 KeyJudgment（分析输出）
```json
{
  "judgment_uid": "jdg_...",
  "case_id": "case_...",
  "judgment_type": "INFERENCE",
  "title": "...",
  "confidence": 0.68,
  "supporting_assertion_uids": ["asn_..."],
  "supporting_source_claim_uids": ["clm_..."],
  "supporting_evidence_uids": ["evi_..."],
  "counter_assertion_uids": ["asn_..."],
  "counter_source_claim_uids": ["clm_..."],
  "gaps": ["Need primary source for ..."],
  "implications": ["Potential escalation risk ..."]
}
```

### 23.3 WatchlistItem（监控输出）
```json
{
  "watch_uid": "w_...",
  "case_id": "case_...",
  "category": "event_trigger",
  "indicator": "Monitor official announcements for ...",
  "trigger_conditions": ["If new NOTAM published", "If exercise zone announced"],
  "linked_entity_uids": ["ent_..."],
  "source_claim_uids": ["clm_..."],
  "evidence_uids": ["evi_..."],
  "priority": "high"
}
```

---

## 24. 总结（一句话）

要做 Palantir 级甚至更强的系统，关键不是“多智能体写更长报告”，而是：

**以 Ontology/Object/SourceClaim/Assertion/Action 为核心，把 OSINT 变成可审计、可回放、可计算的对象平台；多智能体只负责自动化生产结构化工件与补洞审查；Workbench 围绕图谱/时间线/证据回放工作。**
