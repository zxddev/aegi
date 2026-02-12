# CC 任务：P1 本体合同化 + 关系权威模型 + 实体身份版本化

## 背景

当前本体层是"轻量类型列表"，不足以支撑高级分析。需要升级为可执行合同系统。

## 红线（不可违反）

- Evidence-first、SourceClaim-first、Action-only writes（参考 `.kiro/rules/07-ontology.md`）
- 不重写现有模型，做加法
- 所有变更必须有 Alembic migration
- 现有测试不能 break

## 任务 1：本体从类型列表升级为可执行合同

当前状态：`src/aegi_core/db/models/ontology.py` 的 OntologyVersion 只存 entity_types/event_types/relation_types 三个字符串列表。

需要升级为：

```python
# 每个类型不再是纯字符串，而是带约束的定义
class EntityTypeDef(BaseModel):
    name: str                          # 如 "Person", "Organization"
    required_properties: list[str]     # 必填属性，如 ["name"]
    optional_properties: list[str]     # 可选属性
    description: str = ""
    deprecated: bool = False
    deprecated_by: str | None = None   # 被哪个类型替代

class RelationTypeDef(BaseModel):
    name: str                          # 如 "AFFILIATED_WITH"
    domain: list[str]                  # 源实体类型约束，如 ["Person"]
    range: list[str]                   # 目标实体类型约束，如 ["Organization"]
    cardinality: str = "many-to-many"  # one-to-one / one-to-many / many-to-many
    properties: list[str] = []         # 关系属性，如 ["role", "since"]
    temporal: bool = False             # 是否有时间有效期
    description: str = ""
    deprecated: bool = False

class EventTypeDef(BaseModel):
    name: str
    participant_roles: list[str]       # 如 ["actor", "target", "location"]
    required_properties: list[str]
    description: str = ""
    deprecated: bool = False
```

实现要求：
- OntologyVersion 的 entity_types/event_types/relation_types 字段类型从 `list[str]` 改为 `list[dict]`（JSON 存储），向后兼容旧格式
- `ontology_versioning.py` 的兼容性比较升级：不只比较类型名增删，还要比较属性级/约束级 diff
- 新增 `validate_against_ontology(entity/relation, ontology_version)` 函数，在写入时校验是否符合本体约束
- 新增测试：`tests/test_ontology_contract.py`

## 任务 2：RelationFact 权威模型

当前状态：`src/aegi_core/services/relation.py` 的 RelationV1 只有 source/target/type，是轻量二元边。

新增 DB 模型 `src/aegi_core/db/models/relation_fact.py`：

```python
class RelationFact(Base):
    __tablename__ = "relation_facts"

    uid: str                           # PK
    case_uid: str                      # FK -> cases
    source_entity_uid: str             # FK -> entities（如果有实体表）
    target_entity_uid: str
    relation_type: str                 # 必须在当前本体版本的 relation_types 中

    # 证据溯源
    supporting_source_claim_uids: list[str]  # JSON array
    evidence_strength: float           # 0.0 ~ 1.0，基于支撑证据数量和质量
    assessed_by: str                   # "llm" | "expert" | "rule"

    # 时间有效期
    valid_from: datetime | None        # 关系生效时间
    valid_to: datetime | None          # 关系失效时间（None = 仍有效）

    # 冲突
    conflicts_with: list[str]          # 与哪些 relation_fact uid 冲突
    conflict_resolution: str | None    # 冲突解决方式

    # 置信度
    confidence: float                  # 0.0 ~ 1.0

    # 审计
    created_at: datetime
    updated_at: datetime
    created_by_action_uid: str | None  # FK -> actions，追踪是哪个 Action 创建的
```

实现要求：
- Alembic migration
- 在 `graphrag_pipeline.py` 中，写入 Neo4j 之前先写入 RelationFact 权威层
- Neo4j 作为 RelationFact 的投影/索引，不是权威数据源
- 新增 `RelationFactService`：CRUD + 冲突检测 + 证据强度计算
- 冲突检测规则：同一 source+target 如果有矛盾的 relation_type（如 ALLIED_WITH 和 HOSTILE_TO），标记冲突
- 新增测试：`tests/test_relation_fact.py`

## 任务 3：实体身份版本化

当前状态：`entity_disambiguator.py` 用别名表 + embedding 阈值做消歧，没有版本化。

需要增加：

```python
class EntityIdentityAction(Base):
    """记录实体身份变更的 Action。"""
    __tablename__ = "entity_identity_actions"

    uid: str
    action_type: str                   # "merge" | "split" | "create" | "alias_add" | "alias_remove"
    entity_uids: list[str]            # 涉及的实体 uid 列表
    result_entity_uid: str            # merge 后的目标实体 / split 后的新实体
    reason: str                        # 变更原因
    performed_by: str                  # "llm" | "expert" | "rule"
    approved: bool = False             # 是否经过人工审批
    approved_by: str | None = None
    created_at: datetime
```

实现要求：
- Alembic migration
- `entity_disambiguator.py` 中的 merge 操作改为先创建 EntityIdentityAction 记录，再执行实际 merge
- 新增 `rollback_identity_action(action_uid)` 函数：回滚一次 merge/split
- 新增人工审批队列 API：`GET /api/entity-identity/pending`、`POST /api/entity-identity/{uid}/approve`、`POST /api/entity-identity/{uid}/reject`
- 新增测试：`tests/test_entity_identity.py`

## 执行顺序

1. 先做任务 1（本体合同化），因为任务 2 的 relation_type 校验依赖它
2. 再做任务 2（RelationFact）
3. 最后做任务 3（实体身份版本化）

## 验证

每个任务完成后跑：
```bash
source .venv/bin/activate && source env.sh
python -m pytest tests/ -x --tb=short -q \
  --ignore=tests/test_feedback_service.py \
  --ignore=tests/test_stub_routes_integration.py
```

确保全量测试通过。
