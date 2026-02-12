# 修复 test_e2e_proactive_push 节流隔离问题（给 Claude Code）

## 问题

`tests/test_e2e_proactive_push.py::test_proactive_push_via_event_bus` 间歇性失败：

```
assert pl_row.status == "delivered"
AssertionError: assert 'throttled' == 'delivered'
```

原因：同文件中 `test_proactive_push_full_loop` 先跑，往 `push_log` 表写了一条 `expert_bob`（实际是 `expert_alice`，但同一小时窗口内其他 user 也可能触发）的推送记录。第二个测试 `test_proactive_push_via_event_bus` 通过 `create_push_handler()` 创建 PushEngine，使用默认 `max_push_per_hour`（settings 里的值），节流检查查询的是 `push_log` 表最近 1 小时的记录数，导致被节流。

核心问题：两个测试共享同一个 PostgreSQL 数据库，`push_log` 表的残留数据影响了节流判断。

## 在开始编码前，先阅读

- `tests/test_e2e_proactive_push.py` — 问题测试文件
- `src/aegi_core/services/push_engine.py` — PushEngine，重点看 `_is_throttled()` 和 `create_push_handler()`

## 修复方案

在测试文件中添加一个 fixture，每个测试前清理 `push_log` 和 `event_log` 表中的测试残留数据：

```python
@pytest.fixture(autouse=True)
async def _clean_push_logs():
    """清理推送日志，避免节流误判。"""
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        await session.execute(sa.delete(PushLog))
        await session.execute(sa.delete(EventLog))
        await session.commit()
    yield
```

同时，`test_proactive_push_via_event_bus` 中的 `create_push_handler()` 应该传入一个足够大的 `max_push_per_hour`，或者在 settings 中 mock 这个值：

```python
# 在 create_push_handler 调用前
monkeypatch.setattr(settings, "event_push_max_per_hour", 1000)
```

两种方案都做，双保险。

## 验收标准

1. `pytest tests/test_e2e_proactive_push.py -v` 连续跑 3 次都全绿
2. 全量 `pytest` 0 failed
3. 不修改 PushEngine 本身的逻辑
