# GDELT 定时调度实现提示词（给 Claude Code）

## 任务

为 GDELT Monitor 添加定时自动轮询功能，让 AEGI 真正实现"主动监测全球事件"。

当前状态：GDELT Monitor 只有手动 `POST /gdelt/monitor/poll` 端点，没有自动轮询。需要在 app 启动时创建一个后台 asyncio 任务，按 `settings.gdelt_poll_interval_minutes`（默认 15 分钟）定时调用 `GDELTMonitor.poll()`。

**在开始编码前，先完整阅读以下文件：**
- `src/aegi_core/services/gdelt_monitor.py` — GDELTMonitor 实现
- `src/aegi_core/infra/gdelt_client.py` — GDELTClient
- `src/aegi_core/api/main.py` — lifespan 启动逻辑（重点看现有的 EventBus/PushEngine 注册模式）
- `src/aegi_core/api/routes/gdelt.py` — 现有 GDELT 路由
- `src/aegi_core/settings.py` — Settings

## 实现方案

用 asyncio 后台任务，不引入 APScheduler/Celery 等重依赖。

### Step 1：新建 `services/gdelt_scheduler.py`

```python
"""GDELT 定时轮询调度器。"""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class GDELTScheduler:
    """轻量级 GDELT 定时轮询调度器。

    在 app lifespan 中启动，优雅关闭时停止。
    """

    def __init__(
        self,
        monitor: GDELTMonitor,
        *,
        interval_minutes: int = 15,
        enabled: bool = True,
    ) -> None:
        self._monitor = monitor
        self._interval = interval_minutes * 60  # 转为秒
        self._enabled = enabled
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """启动定时轮询后台任务。"""
        if not self._enabled:
            logger.info("GDELT scheduler disabled")
            return
        if self._task is not None:
            logger.warning("GDELT scheduler already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "GDELT scheduler started, interval=%d min",
            self._interval // 60,
        )

    async def stop(self) -> None:
        """优雅停止。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("GDELT scheduler stopped")

    async def _loop(self) -> None:
        """主循环：等待间隔 → poll → 处理异常 → 继续。"""
        # 启动后先等一个间隔再开始第一次轮询（避免启动时立即请求）
        # 如果想启动时立即轮询一次，改为 initial_delay=0
        initial_delay = 60  # 启动后 1 分钟执行第一次
        await asyncio.sleep(initial_delay)

        while self._running:
            try:
                logger.info("GDELT poll starting at %s", datetime.now(timezone.utc).isoformat())
                new_events = await self._monitor.poll()
                logger.info("GDELT poll completed: %d new events", len(new_events))

                # 如果开启了自动 ingest，处理新事件
                from aegi_core.settings import settings
                if settings.gdelt_auto_ingest and new_events:
                    for event in new_events:
                        # 自动 ingest 需要 case_uid，从匹配的 subscription 推断
                        # Phase 1：跳过自动 ingest，只做发现 + 推送通知
                        pass

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("GDELT poll failed, will retry next interval")

            # 等待下一个间隔
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()
```

### Step 2：Settings 新增

```python
# settings.py 新增
gdelt_scheduler_enabled: bool = False  # 默认关闭，需要手动开启
```

注意：默认关闭，避免开发/测试环境自动请求 GDELT API。生产环境通过环境变量 `AEGI_GDELT_SCHEDULER_ENABLED=true` 开启。

### Step 3：lifespan 中启动调度器

在 `api/main.py` 的 lifespan 中，在 EventBus 注册之后、`yield` 之前添加：

```python
# ── GDELT 定时调度（可选）──
from aegi_core.services.gdelt_scheduler import GDELTScheduler
from aegi_core.infra.gdelt_client import GDELTClient
from aegi_core.services.gdelt_monitor import GDELTMonitor

gdelt_scheduler = None
if settings.gdelt_scheduler_enabled:
    gdelt_client = GDELTClient(proxy=settings.gdelt_proxy)
    # GDELTMonitor 需要 db session — 每次 poll 时自己创建
    gdelt_monitor = GDELTMonitor(gdelt_client, db_session=None)  # session 在 poll 内部创建
    gdelt_scheduler = GDELTScheduler(
        gdelt_monitor,
        interval_minutes=settings.gdelt_poll_interval_minutes,
        enabled=True,
    )
    await gdelt_scheduler.start()
```

在 `yield` 之后的关闭逻辑中添加：

```python
if gdelt_scheduler:
    await gdelt_scheduler.stop()
```

**注意：** GDELTMonitor 当前的 `__init__` 接收 `db_session`，但定时任务需要每次 poll 时创建新的 session（避免长连接问题）。需要修改 `GDELTMonitor.poll()` 方法，让它在内部创建 session：

```python
# 如果 self._db 为 None，自己创建 session
if self._db is None:
    from aegi_core.db.session import ENGINE
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        self._db = session
        try:
            return await self._do_poll()
        finally:
            self._db = None
else:
    return await self._do_poll()
```

或者更简洁：给 `GDELTMonitor` 加一个 `poll_with_session()` 类方法，调度器调用这个。

### Step 4：API 端点增强

在 `api/routes/gdelt.py` 中新增：

```python
# POST /gdelt/monitor/start — 运行时启动调度器
# POST /gdelt/monitor/stop — 运行时停止调度器
# GET  /gdelt/monitor/status — 返回调度器状态（running/stopped, last_poll_time, next_poll_time）
```

需要把 `gdelt_scheduler` 实例存到 `app.state` 中，路由才能访问。

### Step 5：测试

1. `tests/test_gdelt_scheduler.py`：
   - `test_scheduler_start_stop` — 启动后 is_running=True，停止后 is_running=False
   - `test_scheduler_calls_poll` — mock GDELTMonitor.poll，验证调度器在间隔后调用了 poll
   - `test_scheduler_handles_poll_error` — poll 抛异常时调度器不崩溃，继续下一轮
   - `test_scheduler_disabled` — enabled=False 时不启动任务
   - `test_scheduler_api_status` — GET /gdelt/monitor/status 返回正确状态

测试策略：
- 用很短的 interval（1 秒）加速测试
- mock GDELTMonitor.poll 避免真实 HTTP 请求
- 用 `asyncio.wait_for` 限制测试时间

## 关键约束

- **不引入新依赖**：纯 asyncio，不用 APScheduler/Celery
- **默认关闭**：`gdelt_scheduler_enabled=False`，避免开发环境自动请求
- **容错**：poll 失败不崩溃，记日志继续下一轮
- **优雅关闭**：app 关闭时等待当前 poll 完成再退出
- **DB session 管理**：每次 poll 创建新 session，不复用长连接
- **现有测试不能 break**

## 验收标准

1. `pytest tests/test_gdelt_scheduler.py` 全绿
2. 全量 `pytest` 0 failed
3. 设置 `AEGI_GDELT_SCHEDULER_ENABLED=true` 启动 app 后，日志中每 15 分钟出现 "GDELT poll starting" / "GDELT poll completed"
4. `GET /gdelt/monitor/status` 返回调度器状态
5. `POST /gdelt/monitor/stop` 能停止调度器
