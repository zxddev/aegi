# AEGI Foundry v0.2 完整规划（需求研究 -> P0 -> P3）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this roadmap task-by-task.

**目标（一句话）**：做一个 OSINT 分析工作台，任何结论都能“点开回源、可审计、可回放、可复现”。

**产品本质**：不是报告生成器，而是证据链驱动的对象平台（Object-first）：
`Judgment → Assertion → SourceClaim → Evidence → Chunk(anchor_set/health) → ArtifactVersion → ArtifactIdentity`。

---

## 0. 不可妥协的不变量（违背就会塌）

这些在 `docs/foundry/v0.2/technical-architecture.md` 已明确，规划/实现必须强制满足：

1) Evidence-first + Archive-first：外部世界进入系统必须先固化版本（ArtifactVersion），禁止“看网页直接写结论”。
2) Action-only writes：所有改变“世界状态”的写入必须通过 Action（审计/回滚/授权）。
3) 强锚点 + 健康度：引用定位是合同，必须抗漂移并可检测漂移。
4) Deny-by-default：模型/工具/导出/高风险动作都要策略显式放行。
5) 派生索引可重建：OpenSearch/Neo4j/Qdrant 等都必须能从 Postgres + 对象存储重建。

---

## 1. 工程形态（Monorepo + 分平面）

**仓库形态（本 repo）**
- `code/aegi-core/`（src layout）：控制面/数据面 + 管线编排 + API
- `code/aegi-mcp-gateway/`（src layout）：工具平面网关 + 适配器 + 工具审计
- `code/aegi-web/`（P1+）：分析师工作台 UI

**端口段（统一 87xx）**
- 应用：`8700` aegi-core，`8704` aegi-mcp-gateway
- 基础设施（docker 映射）：`8710` Postgres，`8711` MinIO API，`8712` MinIO Console
- 可选外部工具（后续接入）：`8701` SearxNG，`8702` ArchiveBox，`8703` Unstructured，`8707` OpenSearch

说明：我们会尽量把“这个项目的一切”都映射到 87xx，避免和系统/其他项目的常用端口冲突。

---

## 2. 多智能体 = 受治理的“编排图”（不是散装 Agent）

**核心原则**：多智能体不是一堆脚本互相调用，而是 LangGraph/状态机式的 pipeline；每个节点都：
- 只能通过 `aegi-mcp-gateway` 调工具
- 每次关键状态变更都写 Action
- 每次工具调用都写 tool_trace
- 任何结构化输出必须能回指 evidence selectors（防幻觉）

**P0 需要的最小节点集合（建议实现为 LangGraph nodes 或等价的可回放 job DAG）**
1) Planner：把 Case 拆成“待验证断言清单 + 采集计划 + 风险/合规策略”。
2) Collector：执行 `meta_search`，产出候选 URL 列表（带选择理由）。
3) Archivist：对 URL 执行 `archive_url`，生成 ArtifactIdentity/Version。
4) Parser：对归档产物执行 `doc_parse_*`，拿到结构化 elements。
5) Chunker：按规则切块，生成 anchor_set + anchor_health。
6) ClaimExtractor：从 chunk 抽 SourceClaim（quote + selectors + attribution + modality）。
7) Fusion：把 SourceClaims 融合成 Assertions（允许冲突集/替代解释）。
8) QA/RedTeam：找“无引用断言、冲突未解释、覆盖不足、锚点漂移”等并回流到 Planner。
9) HITL（P1+）：人工审批/纠错通过 Action 注入。

**验收标准（P0）**：同一 fixtures 输入 + 同一配置 → 可复现同一输出（至少结构化等价），并能 Replay。

---

## 3. 需求研究（把 PRD 变成可验收合同）

**要补齐的文档**：`docs/foundry/v0.2/prd.md` 目前大部分是 TODO，需要变成可执行条目。

### 3.1 P0 必须冻结的 3 个用户流（MVP）

Flow 1：Search → Evidence Vault（可离线演示）
- 给定 query，展示归档后的来源列表（ArtifactVersion），每条可点开产物与 hash。

Flow 2：Citation → SourceClaim（强锚点）
- 点击 SourceClaim，必须能定位到 chunk 的锚点（展示 anchor_health）。

Flow 3：Judgment → 回源
- Judgment 由 Assertions 渲染，点击能回到 SourceClaim/Evidence/ArtifactVersion。

### 3.2 合规与边界（必须工程化）
- OSINT-only、robots/ToS（gateway 强制记录与限速）
- copyright/license（Evidence/Export 必须保留 license_note + restrictions）
- PII 最小化 + case 级 retention

### 3.3 MVP Ontology（对象与关系的最小集合）
- 先定“能支撑 3 个用户流”的最小实体/事件/关系集合
- 先不追求 STIX 全覆盖，但必须规划好后续可映射导入/导出

---

## 4. P0（最小可运行闭环，离线可回归）

### 4.1 基础设施（已完成）
- `docker-compose.yml` + `.env.example`（87xx）
- Postgres + MinIO 能启动（`docker compose ps` 绿色）

### 4.2 P0 数据模型（必须补齐）

最低表清单：
- `cases`
- `artifact_identities` / `artifact_versions`
- `chunks`（anchor_set + anchor_health）
- `evidence`（license_note + pii_flags + retention_policy）
- `source_claims`
- `assertions` + join
- `actions`
- `tool_traces`

验收：
- alembic migration 可创建
- 所有 FK 列有索引
- 每张表至少有最小 round-trip 测试

### 4.3 Gateway 工具合同（先契约后实现）

P0 工具接口（即使先 stub）：
- `/tools/meta_search`
- `/tools/archive_url`
- `/tools/doc_parse`

验收：
- contract tests（输入/输出 schema + 统一错误格式）
- 每次工具调用都有 tool_trace（先结构化日志也行，P0.1 再落库）

### 4.4 Core ↔ Gateway（只走网关）

验收：
- aegi-core 只能通过 ToolClient 调用网关
- aegi-core 任何关键写入都写 Action

### 4.5 离线 fixtures（不做会烂）

固定一组“可复现证据包”到 `code/aegi-core/tests/fixtures/`：
- 归档产物（HTML/PDF/截图/文本）
- 解析产物（elements）
- 预期 chunk anchors

验收：
- anchor locate rate / drift rate 可测
- claim grounding rate 可测

---

## 5. P1（SourceClaim-first 抽取 + 最小工作台）

### 5.1 Chunking + Anchor Health（P1 的硬门槛）
- HTML：TextQuote + TextPosition + XPath/CSS 组合
- PDF：page + bbox + quote

### 5.2 SourceClaim 抽取（结构化输出）
- quote + selectors + attributed_to + modality
- 输出不允许无 selectors（否则直接 reject）

### 5.3 Assertion 融合 + 冲突表达
- 允许冲突集/替代解释，不强行唯一真相

### 5.4 Workbench（只做三视图闭环）
- Evidence Vault
- Claim Compare
- Timeline（基础）

---

## 6. P2（监控/互操作/评测产品化）

### 6.1 Watchlist + 增量更新
- 定时重新采集 → 新版本 → 重跑抽取 → diff

### 6.2 互操作（MISP/OpenCTI/STIX）
- import：MISP event → Evidence/SourceClaim
- export：internal assertions → STIX bundle / MISP mapping

### 6.3 Eval-as-a-Product
- anchor locate/drift
- claim grounding
- extraction 准确率（fixtures 回归）
- latency/cost

---

## 7. P3（协作与规模化）

- RBAC/ABAC + case-scoped tokens
- 派生索引（OpenSearch/Neo4j/Qdrant）可一键重建
- 协作/HITL 审批流

---

## 8. 推荐执行顺序（避免走弯路）

1) 冻结 PRD 的 3 个 P0 用户流 + DoD
2) 做完 P0 闭环 + fixtures（离线可回归）
3) 再上 SourceClaim/Assertion 融合
4) 再上 Workbench UI 扩展

---

## 9. 下一步（你现在就能开工的）

1) 把 `docs/foundry/v0.2/prd.md` 的 Scope/Non-goals/User Stories/FR/NFR/Milestones 写成可验收条目（按 3 个 P0 用户流）
2) 新建一个“P0 数据模型 + tests”专用 plan（细到文件/命令/预期）并执行
