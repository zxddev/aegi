# 任务 4：数据模型与知识图谱一致性审查

> 审查日期: 2026-02-11
> 审查范围: db/models/, infra/neo4j_store.py, infra/qdrant_store.py, services/kg_mapper.py, services/ontology_versioning.py, services/graph_analysis.py, services/entity_disambiguator.py, services/entity_alignment.py, alembic/

---

## 一、数据流向图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          INGESTION PIPELINE                            │
│  Document → parse → Chunk → embed(BGE-M3) → SourceClaim → Assertion   │
└──────┬──────────────────────┬──────────────────────────┬───────────────┘
       │                      │                          │
       ▼                      ▼                          ▼
┌──────────────┐   ┌───────────────────┐   ┌─────────────────────────┐
│  PostgreSQL  │   │   Qdrant (8716)   │   │     Neo4j (8715)        │
│  (8710)      │   │                   │   │                         │
│              │   │ collection:       │   │ Node Labels:            │
│ 16 tables    │   │  aegi_chunks      │   │  Entity, Event,         │
│ (cases,      │   │  dim=1024 COSINE  │   │  Assertion, SourceClaim │
│  artifacts,  │   │  BGE-M3 vectors   │   │                         │
│  chunks,     │   │                   │   │ Relationships:          │
│  evidence,   │   │ payload:          │   │  MERGE by uid           │
│  claims,     │   │  chunk_uid, text, │   │  case_uid scoped        │
│  assertions, │   │  metadata         │   │                         │
│  hypotheses, │   │                   │   │ Indexes:                │
│  narratives, │   │ ID: uuid5(uid)    │   │  Entity.uid/name/type   │
│  reports,    │   │  (deterministic)  │   │  Event.uid/type         │
│  ...)        │   │                   │   │  Assertion.uid          │
│              │   │                   │   │  SourceClaim.uid        │
└──────┬───────┘   └───────────────────┘   └────────────┬────────────┘
       │                                                │
       │  ┌─────────────────────────────────────────┐   │
       └──│  KG Mapper: PG → Neo4j (write-through)  │──┘
          │  Entity Disambiguator: PG audit trail    │
          │  Graph Analysis: Neo4j → networkx (read) │
          │  Ontology: PG + memory cache (dual-write)│
          └─────────────────────────────────────────┘
```

### 关键数据流

```
1. 写入路径:  Document → PG(chunks) → Qdrant(embedding) → PG(claims/assertions) → Neo4j(entities/relations)
2. 查询路径:  User Query → Qdrant(向量检索) → PG(claim/evidence 详情) → Neo4j(图推理/路径)
3. 分析路径:  Neo4j(subgraph) → networkx(社区/中心性/路径) → API 返回
4. 审计路径:  所有服务 → PG(actions + tool_traces)
```

---

## 二、存储分工表

| 存储 | 职责 | 数据类型 | 同步方向 | 一致性保障 |
|------|------|----------|----------|------------|
| PostgreSQL (8710) | 权威数据源 (Source of Truth) | 16 张表：cases, artifacts, chunks, evidence, source_claims, assertions, hypotheses, narratives, judgments, reports, collection_jobs, ontology_versions, case_ontology_pins, actions, tool_traces | — | ACID 事务, FK CASCADE |
| Neo4j (8715) | 图谱推理 + 路径发现 | Entity, Event, Assertion, SourceClaim 节点 + 关系 | PG → Neo4j (单向 write-through) | MERGE by uid (幂等), 无事务绑定 |
| Qdrant (8716) | 向量相似度检索 | aegi_chunks 集合, 1024 维 BGE-M3, COSINE | PG → Qdrant (单向) | uuid5 确定性 ID (幂等), 无事务绑定 |
| Memory Cache | Ontology 快速查询 | _registry + _case_pins | PG ↔ Memory (双写) | 启动时 load_from_db(), 写时双写 |

---

## 三、PostgreSQL 完整模型清单 (16 表)

| # | 表名 | 主键 | 外键 | 关键字段 |
|---|------|------|------|----------|
| 1 | `cases` | uid | — | title, created_at, updated_at |
| 2 | `actions` | uid | case_uid→cases | action_type, actor_id, rationale, inputs(JSONB), outputs(JSONB), trace_id, span_id |
| 3 | `artifact_identities` | uid | — | kind, canonical_url |
| 4 | `artifact_versions` | uid | artifact_identity_uid→artifact_identities, case_uid→cases | storage_ref, content_sha256, content_type, source_meta(JSONB) |
| 5 | `chunks` | uid | artifact_version_uid→artifact_versions | ordinal, text, anchor_set(JSONB), anchor_health(JSONB) |
| 6 | `evidence` | uid | case_uid→cases, artifact_version_uid, chunk_uid | kind, license_note, pii_flags(JSONB), retention_policy(JSONB) |
| 7 | `source_claims` | uid | case_uid, artifact_version_uid, chunk_uid, evidence_uid | quote, selectors(JSONB), attributed_to, modality, language, original_quote, translation, translation_meta(JSONB) |
| 8 | `assertions` | uid | case_uid→cases | kind, value(JSONB), source_claim_uids(JSONB), confidence, modality |
| 9 | `hypotheses` | uid | case_uid→cases | label, supporting/contradicting_assertion_uids(JSONB), coverage_score, confidence, gap_list(JSONB), adversarial_result(JSONB), trace_id, prompt_version |
| 10 | `judgments` | uid | case_uid→cases | title, assertion_uids(JSONB) |
| 11 | `narratives` | uid | case_uid→cases | theme, source_claim_uids(JSONB), first_seen_at, latest_seen_at |
| 12 | `reports` | uid | case_uid→cases | report_type, title, sections(JSONB), rendered_markdown, config(JSONB), trace_id |
| 13 | `collection_jobs` | uid | case_uid→cases | query, categories, language, max_results, status, urls_found/ingested/deduped, claims_extracted, cron_expression |
| 14 | `ontology_versions` | version | — | entity_types(JSONB), event_types(JSONB), relation_types(JSONB) |
| 15 | `case_ontology_pins` | case_uid | case_uid→cases | ontology_version, pinned_at |
| 16 | `tool_traces` | uid | case_uid→cases, action_uid→actions | tool_name, request(JSONB), response(JSONB), status, duration_ms, error, trace_id, span_id |

所有外键均设置 `ondelete=CASCADE`，所有表均有 `created_at` 时间戳。

---

## 四、Neo4j 图谱结构

### 节点标签与索引

| 标签 | 索引字段 | 来源 |
|------|----------|------|
| Entity | uid, name, type | KG Mapper 提取 |
| Event | uid, type | KG Mapper 提取 |
| Assertion | uid | Pipeline 同步 |
| SourceClaim | uid | Pipeline 同步 |

### Neo4j Store 方法清单

| 方法 | 类型 | 用途 |
|------|------|------|
| `upsert_nodes(label, rows)` | 写 | MERGE 节点 by uid, SET 属性 |
| `upsert_edges(src_label, tgt_label, rel_type, edges)` | 写 | MERGE 关系 |
| `get_neighbors(node_uid, limit=50)` | 读 | 获取邻居节点 |
| `find_path(source_uid, target_uid, max_depth=5)` | 读 | 最短路径 |
| `search_entities(keywords, case_uid, limit=10)` | 读 | 模糊搜索 |
| `get_subgraph(case_uid, limit=5000)` | 读 | 提取 case 全子图 |
| `get_temporal_events(case_uid, start, end, limit=200)` | 读 | 时间线事件 |
| `find_multi_hop_paths(src, tgt, max_depth=5, limit=10)` | 读 | 多跳路径 |
| `get_isolated_nodes(case_uid, limit=100)` | 读 | 孤立节点 |
| `get_entity_timeline(entity_uid, limit=100)` | 读 | 实体时间线 |
| `get_relationship_stats(case_uid)` | 读 | 关系类型分布 |
| `count_nodes()` | 读 | 节点/关系计数 |
| `delete_all()` | 写 | 清空图谱 |

---

## 五、Qdrant 向量存储

| 配置项 | 值 |
|--------|-----|
| 集合名 | `aegi_chunks` |
| 向量维度 | 1024 |
| 距离度量 | COSINE |
| Embedding 模型 | BGE-M3 |
| Point ID 策略 | `uuid5(NAMESPACE_URL, chunk_uid)` (确定性, 幂等) |

**Payload 结构**: `{ chunk_uid, text, metadata }` — metadata 包含 case_uid、source 等上下文信息。

**方法**: `upsert(chunk_uid, embedding, text, metadata)`, `upsert_batch(points)`, `search(query_embedding, limit, score_threshold)`, `delete(chunk_uid)`

Embedding 在外部生成（LLMClient 或独立 embedding 服务），传入 store 的 upsert 方法。Qdrant 本身不生成 embedding。

---

## 六、实体消歧与跨语言对齐

### 6.1 实体消歧 (`entity_disambiguator.py`)

**目标**: 识别 KG 中指向同一现实实体的重复节点。

**两阶段算法**:

| 阶段 | 方法 | 置信度 | 不确定阈值 |
|------|------|--------|------------|
| Stage 1 | 规则归一化 (NFKC→lowercase→去标点→折叠空格) + 别名表查找 | 0.95 | — |
| Stage 2 | Embedding 余弦相似度 (≥0.82 合并) | avg_sim | <0.7 标记 uncertain |

**别名表** (硬编码):
```
PRC / 中华人民共和国 / 中国 → china
DPRK → north korea | ROK → south korea
USA / US / 美国 → united states
俄罗斯 / RF / Russian Federation → russia
EU → european union | NATO → north atlantic treaty organization
UN / 联合国 → united nations
```

**输出**: `MergeGroup(canonical_uid, alias_uids, confidence, uncertain, explanation)`

**关键原则**: confidence < 0.7 标记 `uncertain=True`，不自动合并，需人工审核。

### 6.2 跨语言实体对齐 (`entity_alignment.py`)

**目标**: 识别不同语言文本片段指向同一实体的情况。

**算法**:
1. 规则候选生成: 按 normalized quote (lowercase + strip) 分组
2. LLM Rerank: 对 ≥2 成员的组调用 LLM 判断 "Are these text fragments referring to the same entity?"
3. LLM 返回 `{score, explanation}`，fallback: 2 成员组 0.85, 更大组 0.6

**输出**: `EntityLinkV1(canonical_id, alias_text, language, source_claim_uid, confidence, uncertain, explanation)`

### 6.3 完整性评估

| 维度 | 状态 | 说明 |
|------|------|------|
| 算法实现 | ✅ 完整 | 规则 + 语义双阶段 |
| 别名表 | ⚠️ 硬编码 | 仅覆盖主要国家/组织，无动态扩展 |
| 消歧结果回写 Neo4j | ❌ 缺失 | MergeGroup 仅写审计记录，无自动执行合并 |
| 对齐结果持久化 | ❌ 缺失 | EntityLinkV1 无持久化表，无状态服务 |
| LLM 降级 | ✅ 有 fallback | LLM 不可用时使用规则分数 |

---

## 七、Ontology Versioning

### 版本管理策略

| 特性 | 实现 |
|------|------|
| 版本格式 | 语义化版本 (如 "1.0.0") |
| 版本内容 | entity_types[], event_types[], relation_types[] |
| 存储 | PG `ontology_versions` 表 + 内存 `_registry` 缓存 |
| Case 绑定 | PG `case_ontology_pins` 表 + 内存 `_case_pins` 缓存 |

### 兼容性检测

| 变更级别 | 触发条件 | 自动升级 |
|----------|----------|----------|
| COMPATIBLE | 仅新增类型 | ✅ 允许 |
| DEPRECATED | 有类型标记废弃 | ⚠️ 需确认 |
| BREAKING | 有类型被移除 | ❌ 需 `approved=True` |

### Schema 演进能力评估

- ✅ 能检测 entity/event/relation 类型的增删
- ✅ Case 级别 pin 防止跨版本读取
- ✅ Breaking 变更需显式审批
- ⚠️ 多进程部署时内存缓存可能短暂不一致（有 DB fallback 兜底）
- ❌ 不支持字段级别的 schema 变更检测（仅类型级别）
- ❌ 无自动数据迁移（仅提供 migration_plan 文本）

---

## 八、Alembic Migration 一致性

### Migration 链 (10 个)

| # | Revision | 日期 | 内容 |
|---|----------|------|------|
| 1 | `bc5052692a40` | 2026-01-01 | init (空占位) |
| 2 | `3f52046a1239` | 2026-01-15 | cases + actions 表 |
| 3 | `01195e08d027` | 2026-01-20 | P0 证据链 8 张表 (artifacts, chunks, evidence, source_claims, assertions, judgments, hypotheses, narratives) |
| 4 | `a2e59547cc18` | 2026-01-25 | tool_traces 表 |
| 5 | `1dda8adf4f9b` | 2026-02-06 | Foundation gate-0 字段 (segment_ref, media_time_range, trace_id, span_id) |
| 6 | `7b3e2a1f5c09` | 2026-02-06 | 多语言字段 (language, original_quote, translation, translation_meta) |
| 7 | `c4a7e3b21d06` | 2026-02-07 | ontology_versions + case_ontology_pins 表 |
| 8 | `377e829ab430` | 2026-02-08 | hypotheses 多模态字段 |
| 9 | `9a1b2c3d4e5f` | 2026-02-10 | reports 表 |
| 10 | `b2c3d4e5f6a7` | 2026-02-11 | collection_jobs 表 + dedup 索引 |

### 一致性结论

- ✅ 10 个 migration 的最终 schema 覆盖全部 16 个 ORM 模型的所有字段
- ✅ 无遗漏的 migration
- ⚠️ Migration #3 和 #6 存在冗余: source_claims 的多语言字段在 #3 已定义，#6 用 `_add_col_if_missing()` 重复添加（幂等，无功能影响）

---

## 九、各服务存储交互矩阵

| 服务 | PostgreSQL | Neo4j | Qdrant | LLM | 审计记录 |
|------|------------|-------|--------|-----|----------|
| kg_mapper | ✅ action/trace | ✅ upsert nodes/edges | — | ✅ structured extract | ✅ ActionV1 + ToolTraceV1 |
| entity_disambiguator | ✅ action/trace | ❌ 不回写 | — | ✅ embed() | ✅ ActionV1 + ToolTraceV1 |
| entity_alignment | — | — | — | ✅ invoke() rerank | ✅ (via caller) |
| ontology_versioning | ✅ versions/pins | — | — | — | ✅ ActionV1 + ToolTraceV1 |
| graph_analysis | — | ✅ read subgraph | — | — | — |
| neo4j_store | — | ✅ CRUD | — | — | — |
| qdrant_store | — | — | ✅ CRUD | — | — |

---

## 十、一致性风险清单

### 风险 1: PG ↔ Neo4j 无事务绑定

- **严重度**: 🔴 高
- **描述**: KG Mapper 先写 PG (ORM commit)，再调 `neo4j.upsert_nodes()` + `upsert_edges()`。Neo4j 写入失败时 PG 已提交但图谱缺数据。
- **影响**: 图分析结果不完整，路径发现遗漏实体
- **现状**: 无补偿机制、无重试队列、无一致性校验
- **建议**: 增加 outbox 模式或后台 reconciliation job，定期比对 PG entity 数量 vs Neo4j node 数量

### 风险 2: PG ↔ Qdrant 无事务绑定

- **严重度**: 🔴 高
- **描述**: Chunk 写入 PG 后独立 upsert 到 Qdrant。Embedding 生成或 Qdrant 写入失败时，PG 有 chunk 但向量检索找不到。
- **影响**: 向量检索召回率下降，部分文档"隐形"
- **现状**: uuid5 确定性 ID 保证幂等重试，但无自动重试机制
- **建议**: 增加 chunk 的 `indexed_at` 字段，后台扫描未索引 chunk 补写

### 风险 3: Entity/Relation 在 PG 无独立表

- **严重度**: 🟡 中
- **描述**: EntityV1, EventV1, RelationV1 是 Pydantic 模型，仅存在于 Neo4j 节点和 PG 的 JSONB 字段中。PG 没有 `entities` / `relations` 表。
- **影响**: 无法用 SQL 查询实体列表、无法做 PG 级别的实体去重统计、无法用 FK 约束保证引用完整性
- **建议**: 如需 PG 级别实体管理，考虑增加 `entities` 和 `relations` 表作为 Neo4j 镜像

### 风险 4: 实体消歧结果未自动回写 Neo4j

- **严重度**: 🟡 中
- **描述**: `entity_disambiguator.py` 输出 MergeGroup 但只写 PG 审计记录。实际 Neo4j 节点合并需下游消费者执行。
- **影响**: 消歧结果可能被忽略，图谱持续存在重复节点
- **现状**: 无自动 merge 执行器
- **建议**: 增加 `apply_merge_groups()` 方法，在 pipeline 中自动执行 Neo4j 节点合并

### 风险 5: 跨语言对齐结果无持久化

- **严重度**: 🟡 中
- **描述**: `entity_alignment.py` 是无状态服务，输出 EntityLinkV1 列表但不写入任何存储。
- **影响**: 重复计算、无法追溯历史对齐决策
- **建议**: 增加 `entity_links` 表存储对齐结果

### 风险 6: Ontology 内存缓存多进程不一致

- **严重度**: 🟢 低
- **描述**: 多进程部署时，进程 A 写入新版本到 PG + 自身内存，进程 B 内存缓存仍是旧版本。
- **现状**: `get_version_db()` 有 DB fallback (cache miss 时查 DB)，但 `get_version()` 纯内存
- **建议**: 统一使用 `_db` 后缀方法，或增加 TTL 缓存失效

### 风险 7: Alembic migration 冗余

- **严重度**: 🟢 低
- **描述**: Migration #3 和 #6 对 source_claims 多语言字段重复定义，#6 用 `_add_col_if_missing()` 做了幂等处理。
- **影响**: 无功能影响，仅代码整洁度问题

### 风险 8: Embedding 模型硬编码

- **严重度**: 🟢 低
- **描述**: Qdrant 集合固定 1024 维 (BGE-M3)。切换 embedding 模型需重建整个集合。
- **建议**: 将维度配置化，或在集合名中包含模型标识 (如 `aegi_chunks_bge_m3`)

---

## 十一、问题总结

| # | 问题 | 结论 |
|---|------|------|
| Q1 | PG ↔ Neo4j 同步机制 | 单向 write-through, MERGE by uid 幂等, **无事务绑定, 无补偿机制** |
| Q2 | 实体消歧/跨语言对齐 | 算法完整 (规则+语义双阶段), 但消歧结果未回写 Neo4j, 对齐结果无持久化 |
| Q3 | Qdrant embedding 策略 | BGE-M3, 1024 维, COSINE, 外部生成 embedding, uuid5 确定性 ID |
| Q4 | Ontology schema 演进 | 支持类型级别增删检测 + case pin + breaking 审批, 不支持字段级别变更 |
| Q5 | Alembic 与模型一致性 | ✅ 一致, 10 个 migration 覆盖全部 16 个模型, 有一处冗余但已幂等处理 |
