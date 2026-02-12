# 事件驱动层实现说明

> 日期：2026-02-11
> 基于：event-driven-architecture-guide.md + event-driven-layer.md

## 实现清单

### 新增文件（8个）

| 文件 | 说明 |
|------|------|
| `db/models/subscription.py` | Subscription 模型 |
| `db/models/event_log.py` | EventLog 模型 |
| `db/models/push_log.py` | PushLog 模型 |
| `services/event_bus.py` | EventBus 事件总线（asyncio 内存实现） |
| `services/push_engine.py` | PushEngine 推送决策引擎 + create_push_handler 工厂 |
| `api/routes/subscriptions.py` | Subscription CRUD API（POST/GET/PATCH/DELETE） |
| `alembic/versions/c3d4e5f6a7b8_add_event_driven_tables.py` | 3张表的 migration |
| `tests/test_event_bus.py` | EventBus 单元测试（12个） |
| `tests/test_push_engine.py` | PushEngine 单元测试（12个） |
| `tests/test_event_driven_integration.py` | 集成测试（8个） |

### 修改文件（6个）

| 文件 | 改动 |
|------|------|
| `db/models/__init__.py` | 导出 EventLog, PushLog, Subscription |
| `settings.py` | 新增 event_push_max_per_hour, event_push_semantic_threshold, event_push_expert_collection |
| `api/main.py` | lifespan 初始化 EventBus + 注册 PushEngine handler + 独立 expert_profiles QdrantStore + drain shutdown + subscriptions router |
| `services/pipeline_orchestrator.py:186` | emit pipeline.completed 事件 |
| `services/stages/osint_collect.py:61` | emit osint.collected 事件 |
| `services/claim_extractor.py:193` | emit claim.extracted 事件 |

## 审查意见落实

| 编号 | 要求 | 实现 |
|------|------|------|
| A | PushEngine 语义匹配使用独立 QdrantStore（expert_profiles 集合） | main.py lifespan 中创建独立 QdrantStore(collection=settings.event_push_expert_collection)，传入 create_push_handler |
| B | _deliver 调用 notify_user 前确认签名 | 已读 dispatch.py:60-74，签名为 `notify_user(user_id, message, *, label="system")`，调用时传 `label="event_push"` |
| C | claim.extracted 的 source_event_uid 加时间戳 | `f"claim:{case_uid}:{chunk_uid}:{int(time.time())}"` |
| D | 新增 subscriptions CRUD API | api/routes/subscriptions.py，POST/GET/PATCH/DELETE，风格与 collection.py 一致 |

## 测试结果

```
299 passed, 26 skipped, 2 warnings in 90.03s
```

新增 32 个测试（12 event_bus + 12 push_engine + 8 integration），全部通过。
