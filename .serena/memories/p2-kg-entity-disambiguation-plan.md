# P2 知识图谱 — 实体消歧功能计划

## 背景
- P2 验收要求"自动化知识图谱构建（含实体消歧基础能力）"
- `kg_mapper.build_graph()` 当前按 `attributed_to` 精确匹配去重，"China"/"PRC"/"中国" 会创建 3 个独立实体
- `entity_alignment.py` 是 P1 的跨语言 claim 对齐，不是实体消歧

## 已完成 ✅ 全部完成
- `build_from_assertions` API 已写入 Neo4j（MERGE 幂等，支持增量）
- Neo4jStore 有完整的 upsert_nodes/upsert_edges/get_neighbors/find_path
- `entity_disambiguator.py` 服务实现（规则归一化 + embedding 语义相似度 + 审计）
- `kg.py` 路由 `POST /cases/{case_uid}/kg/disambiguate`（含 Neo4j SAME_AS 写入）
- 14 单元测试（归一化、别名表、规则层合并、语义层 mock embedding、容错）
- 1 API 集成测试（test_disambiguate_api）
- 197 passed, 0 failed

## 设计方案

### 新建 `services/entity_disambiguator.py`
- 输入：`list[EntityV1]`（来自 `build_graph()` 输出）
- 输出：消歧结果，包含 merge 建议组（canonical_uid + alias_uids + confidence + explanation）
- 规则层：label 归一化（大小写、空格、标点）+ 已知别名表（可扩展）
- 语义层：用 `LLMClient.embed()` 计算 entity label 的 embedding 相似度，高于阈值的归为候选组
- 遵循项目原则：低置信度（< 0.7）标记为 uncertain，不自动合并
- 审计：返回 ActionV1 + ToolTraceV1

### 集成点
- `kg.py` route `build_from_assertions` 成功后，可选调用消歧
- 消歧结果写入 Neo4j：为 merge 组创建 `SAME_AS` 关系（不删除原节点）
- 或者独立 API endpoint：`POST /cases/{case_uid}/kg/disambiguate`

### 参考模式
- `entity_alignment.py` 的 "规则候选 + LLM rerank" 模式
- `hypothesis_adversarial.py` 的 LLM 调用 + grounding gate 模式
- `kg_mapper.py` 的 ActionV1/ToolTraceV1 审计模式

### EntityV1 可能需要扩展
- 加 `canonical_uid: str | None` 字段（指向消歧后的主实体）
- 或者不改 EntityV1，只在 Neo4j 中用 SAME_AS 关系表达

## 项目约定
- `# Author: msq` 文件头
- 中文注释
- ruff lint+format
- pytest+pytest-asyncio, asyncio_mode=auto
- 架构红线：Evidence-first, SourceClaim-first, Action-only writes
