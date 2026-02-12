# GDELT + CAMEO 数据源接入 — 架构指导

> 日期：2026-02-11
> 作者：白泽
> 状态：架构指导，待详细设计

---

## 一、目标

让 AEGI 从"被动等人喂数据"变成"主动监测全球事件"。

GDELT（Global Database of Events, Language, and Tone）是目前最大的开放全球事件数据库，每 15 分钟更新一次，覆盖全球新闻源。接入 GDELT 后，AEGI 可以：

1. 自动发现与专家关注领域相关的新事件
2. 新事件 → 自动提取 claim → 触发贝叶斯 ACH 更新 → 推送给专家
3. 构建事件时间线，发现趋势和异常

这是事件驱动层 + 贝叶斯 ACH 的上游数据源，三者串起来就是 AEGI 的核心闭环。

---

## 二、GDELT 数据源概述

### 2.1 可用接口

| 接口 | 更新频率 | 格式 | 用途 |
|------|---------|------|------|
| GDELT 2.0 Events（CSV） | 每 15 分钟 | CSV/ZIP | 结构化事件记录（谁对谁做了什么） |
| GDELT GKG（Global Knowledge Graph） | 每 15 分钟 | CSV/ZIP | 主题/人物/组织/情感/引用 |
| GDELT DOC API | 实时 | JSON | 按关键词搜索近期新闻文章 |
| GDELT GEO API | 实时 | JSON | 按地理位置搜索事件 |
| GDELT TV API | 实时 | JSON | 电视新闻监控（不需要） |

### 2.2 推荐接入方式

**Phase 1（先做）：GDELT DOC API** — 最简单，JSON 格式，按关键词搜索，不需要下载大文件。适合"按专家关注主题拉取相关新闻"。

**Phase 2（后做）：GDELT 2.0 Events CSV** — 结构化事件数据，包含 CAMEO 编码。适合"全量监测特定地区/行为类型的事件"。需要定时下载 + 解析 CSV。

**暂不接入：** GKG（太重，单次 dump 几百 MB）、TV API（不需要）。

### 2.3 CAMEO 编码体系

CAMEO（Conflict and Mediation Event Observations）是 GDELT 事件的行为分类编码：

```
01 - 公开声明          11 - 拒绝
02 - 呼吁              12 - 威胁
03 - 表达合作意向       13 - 抗议
04 - 咨询              14 - 暴力行为
05 - 外交合作          15 - 使用武力
06 - 物质合作          17 - 军事行动
07 - 提供援助          18 - 胁迫
08 - 让步              19 - 大规模暴力
09 - 调查              20 - 大规模杀伤
10 - 要求
```

Goldstein Scale：-10（极端冲突）到 +10（极端合作），量化事件的冲突/合作程度。

---

## 三、架构设计

### 3.1 整体流程

```
专家订阅（Subscription）
    │ 关注主题/地区/实体
    ▼
GDELTMonitor（定时任务）
    │ 每 15 分钟轮询 GDELT DOC API
    │ 按订阅的关键词搜索
    ▼
GDELTEvent 结构化数据
    │
    ├─ 去重（URL hash）
    ├─ 相关性过滤（与订阅匹配度）
    ▼
EventBus.emit("gdelt.event_detected")
    │
    ├─ handler 1: 自动创建 Evidence + SourceClaim
    │     └─ emit("claim.extracted") → 触发贝叶斯 ACH 更新
    │
    ├─ handler 2: 写入事件时间线（Narrative）
    │
    └─ handler 3: 异常检测（Goldstein Scale 突变）
          └─ emit("gdelt.anomaly_detected") → 高优先级推送
```

### 3.2 新增组件

```
infra/gdelt_client.py          — GDELT API 客户端（纯 HTTP）
services/gdelt_monitor.py      — 监控调度 + 事件处理逻辑
db/models/gdelt_event.py       — GDELT 事件存储（去重用）
api/routes/gdelt.py            — 手动触发 + 查询 API
```

### 3.3 不新增组件（复用现有）

- `CollectionJob` — 已有 cron_expression 字段，可复用做定时调度
- `EventBus` — 已有，直接 emit 新事件类型
- `Subscription` — 已有，专家订阅机制直接复用
- `PushEngine` — 已有，匹配订阅 → 推送
- `OSINTCollector` — 已有，GDELT 发现的 URL 可以走 OSINT 流程深度采集

---

## 四、数据模型

### 4.1 gdelt_events 表

```python
class GdeltEvent(Base):
    __tablename__ = "gdelt_events"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    gdelt_id: Mapped[str] = mapped_column(
        sa.String(128), unique=True, nullable=False,
        comment="GDELT 原始事件 ID 或 URL hash，用于去重"
    )
    case_uid: Mapped[str | None] = mapped_column(
        sa.String(64), sa.ForeignKey("cases.uid", ondelete="SET NULL"),
        index=True, comment="关联的 case（可为空，后续关联）"
    )

    # 事件核心字段
    title: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    url: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    source_domain: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    language: Mapped[str] = mapped_column(sa.String(16), default="en")
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    # CAMEO 编码（Phase 2 才有，Phase 1 可为空）
    cameo_code: Mapped[str | None] = mapped_column(sa.String(8))
    cameo_root: Mapped[str | None] = mapped_column(
        sa.String(4), index=True, comment="CAMEO 根编码，如 14=暴力行为"
    )
    goldstein_scale: Mapped[float | None] = mapped_column(sa.Float())

    # 实体
    actor1: Mapped[str | None] = mapped_column(sa.String(256))
    actor2: Mapped[str | None] = mapped_column(sa.String(256))
    actor1_country: Mapped[str | None] = mapped_column(sa.String(8), index=True)
    actor2_country: Mapped[str | None] = mapped_column(sa.String(8), index=True)

    # 地理
    geo_lat: Mapped[float | None] = mapped_column(sa.Float())
    geo_lon: Mapped[float | None] = mapped_column(sa.Float())
    geo_country: Mapped[str | None] = mapped_column(sa.String(8), index=True)
    geo_name: Mapped[str | None] = mapped_column(sa.String(256))

    # 情感/基调
    tone: Mapped[float | None] = mapped_column(
        sa.Float(), comment="GDELT tone score，负=消极，正=积极"
    )

    # 处理状态
    status: Mapped[str] = mapped_column(
        sa.String(16), default="new", nullable=False,
        comment="new | ingested | skipped | error"
    )
    matched_subscription_uids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False,
        comment="匹配到的订阅 UID 列表"
    )

    raw_data: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False,
        comment="GDELT 原始 JSON 响应"
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
```

### 4.2 索引策略

```python
__table_args__ = (
    sa.Index("ix_gdelt_country_cameo", "geo_country", "cameo_root"),
    sa.Index("ix_gdelt_published", "published_at"),
    sa.Index("ix_gdelt_status", "status"),
)
```

---

## 五、GDELT DOC API 客户端

### 5.1 接口

```python
class GDELTClient:
    """GDELT DOC API 客户端。"""

    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, proxy: str | None = None) -> None:
        """proxy: 如 'http://127.0.0.1:7890'，国内服务器需要。"""

    async def search_articles(
        self,
        query: str,
        *,
        mode: str = "ArtList",        # ArtList | TimelineVol | TimelineTone
        timespan: str = "15min",       # 15min | 1h | 1d | 7d ...
        max_records: int = 50,
        source_country: str | None = None,
        source_lang: str | None = None,
        sort: str = "DateDesc",
    ) -> list[GDELTArticle]: ...

    async def search_events_by_theme(
        self,
        theme: str,
        *,
        timespan: str = "1h",
    ) -> list[GDELTArticle]: ...
```

### 5.2 GDELTArticle 数据类

```python
@dataclass
class GDELTArticle:
    url: str
    title: str
    source_domain: str
    language: str
    seendate: str              # "20260211T153000Z"
    socialimage: str = ""
    tone: float = 0.0          # 基调分数
    domain_country: str = ""   # 来源国家
```

### 5.3 注意事项

- GDELT DOC API 无需 API key，免费使用
- 有速率限制（不明确，建议间隔 5 秒以上）
- 国内服务器需要走代理（`settings.py` 已有 proxy 配置模式，参考 `127.0.0.1:7890`）
- 返回的是新闻文章列表，不是结构化事件（CAMEO 编码在 Events CSV 里）

---

## 六、GDELTMonitor 监控服务

### 6.1 核心逻辑

```python
class GDELTMonitor:
    """GDELT 事件监控器。

    定时轮询 GDELT DOC API，按专家订阅的关键词搜索，
    发现新事件后 emit 到 EventBus。
    """

    def __init__(
        self,
        gdelt: GDELTClient,
        db_session: AsyncSession,
    ) -> None: ...

    async def poll(self) -> list[GdeltEvent]:
        """单次轮询流程：

        1. 加载所有 active 的 Subscription
        2. 提取唯一的关键词集合（去重）
        3. 对每个关键词调 GDELT DOC API
        4. 去重（gdelt_id = URL hash）
        5. 匹配订阅（哪些订阅关注了这个事件）
        6. 持久化到 gdelt_events 表
        7. emit "gdelt.event_detected" 事件
        8. 返回新发现的事件列表
        """

    async def ingest_event(
        self,
        event: GdeltEvent,
        case_uid: str,
    ) -> None:
        """将 GDELT 事件转化为 AEGI 的 Evidence + SourceClaim。

        1. 用 OSINTCollector 抓取文章全文
        2. 创建 Evidence 记录
        3. 提取 SourceClaim（LLM claim extraction）
        4. emit "claim.extracted" → 触发贝叶斯 ACH
        """
```

### 6.2 订阅匹配

复用现有 `Subscription` 模型。专家订阅时可以指定：

```json
{
  "event_types": ["gdelt.event_detected"],
  "match_rules": {
    "keywords": ["伊朗", "核谈判"],
    "countries": ["IR", "US"],
    "cameo_roots": ["14", "15", "17"]
  }
}
```

匹配逻辑：
- 关键词匹配：标题或摘要包含任一关键词
- 国家匹配：actor1_country 或 actor2_country 或 geo_country 匹配
- CAMEO 匹配：cameo_root 匹配（Phase 2）
- 任一条件命中即匹配

### 6.3 去重策略

```python
gdelt_id = hashlib.sha256(article.url.encode()).hexdigest()[:32]
```

用 URL hash 去重。`gdelt_events.gdelt_id` 有 unique 约束，重复插入直接跳过。

### 6.4 异常检测

简单规则，不需要 ML：

```python
async def detect_anomaly(self, events: list[GdeltEvent]) -> list[GdeltEvent]:
    """检测异常事件。

    规则：
    1. Goldstein Scale < -7（严重冲突事件）
    2. 同一地区 1 小时内事件数突增 > 3 倍历史均值
    3. 新出现的 actor 对（之前没有互动记录的两个国家/组织）

    异常事件 emit "gdelt.anomaly_detected"，severity="high"
    """
```

---

## 七、定时调度

### 7.1 方案：复用 CollectionJob

不新建调度机制。在 `CollectionJob` 表中创建 GDELT 类型的 job：

```python
# 创建 GDELT 监控任务
job = CollectionJob(
    uid=generate_uid(),
    case_uid=case_uid,          # 可为空（全局监控）
    query="gdelt_monitor",      # 特殊标记
    categories="gdelt",         # 区分 OSINT 和 GDELT
    cron_expression="*/15 * * * *",  # 每 15 分钟
    status="pending",
)
```

### 7.2 调度器

在 `api/main.py` lifespan 中启动一个 asyncio 后台任务：

```python
async def gdelt_scheduler(app_state):
    """每分钟检查是否有到期的 GDELT CollectionJob。"""
    while True:
        await asyncio.sleep(60)
        # 查询 next_run_at <= now 的 GDELT job
        # 执行 GDELTMonitor.poll()
        # 更新 last_run_at 和 next_run_at
```

这个调度器很轻量，不需要 Celery 或 APScheduler。

---

## 八、事件类型

新增两个事件类型：

| 事件类型 | 触发时机 | severity | payload |
|---------|---------|----------|---------|
| `gdelt.event_detected` | 发现新的相关事件 | low/medium | `{title, url, source_domain, tone, matched_keywords, geo_country}` |
| `gdelt.anomaly_detected` | 检测到异常事件 | high | `{title, url, goldstein_scale, anomaly_type, description}` |

下游 handler：
- `gdelt.event_detected` → PushEngine 匹配订阅推送 + 可选自动 ingest
- `gdelt.anomaly_detected` → PushEngine 高优先级推送

---

## 九、Settings 新增

```python
# settings.py 新增
gdelt_proxy: str = "http://127.0.0.1:7890"    # GDELT API 代理
gdelt_poll_interval_minutes: int = 15           # 轮询间隔
gdelt_max_articles_per_query: int = 50          # 每次查询最大文章数
gdelt_auto_ingest: bool = False                 # 是否自动将事件转为 Evidence
gdelt_anomaly_goldstein_threshold: float = -7.0 # Goldstein 异常阈值
```

---

## 十、与现有系统的集成点

```
Subscription（已有）
    │ 专家关注的关键词/地区
    ▼
GDELTMonitor.poll()（新增）
    │ 按关键词查 GDELT → 去重 → 匹配订阅
    ▼
EventBus.emit("gdelt.event_detected")（已有机制）
    │
    ├─→ PushEngine（已有）→ 推送给匹配的专家
    │
    ├─→ GDELTMonitor.ingest_event()（新增）
    │     │
    │     ├─→ OSINTCollector.collect()（已有）→ 抓全文
    │     └─→ emit("claim.extracted")（已有）
    │           │
    │           └─→ BayesianACH.update()（正在实现）→ 概率更新
    │
    └─→ detect_anomaly()（新增）
          └─→ emit("gdelt.anomaly_detected") → 高优先级推送
```

关键点：GDELT 接入不需要改动任何现有代码，只是在上游增加一个数据源，通过 EventBus 接入已有的事件驱动链路。

---

## 十一、API 端点

```
POST /gdelt/monitor/start          — 启动 GDELT 监控（创建 CollectionJob）
POST /gdelt/monitor/stop           — 停止监控
POST /gdelt/monitor/poll           — 手动触发一次轮询
GET  /gdelt/events                 — 查询已发现的 GDELT 事件（分页、过滤）
GET  /gdelt/events/{uid}           — 单个事件详情
POST /gdelt/events/{uid}/ingest    — 手动将事件转为 Evidence
GET  /gdelt/stats                  — 统计：事件数、国家分布、时间趋势
```

---

## 十二、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `infra/gdelt_client.py` | 新建 | GDELT DOC API 客户端 |
| `services/gdelt_monitor.py` | 新建 | 监控调度 + 事件处理 + 异常检测 |
| `db/models/gdelt_event.py` | 新建 | GdeltEvent 模型 |
| `db/models/__init__.py` | 修改 | 导出 GdeltEvent |
| `api/routes/gdelt.py` | 新建 | 7 个 API 端点 |
| `api/main.py` | 修改 | 注册路由 + 启动调度器 |
| `settings.py` | 修改 | 新增 5 个配置项 |
| `alembic/versions/xxx_gdelt.py` | 新建 | Migration |
| `tests/test_gdelt_client.py` | 新建 | API 客户端测试（mock HTTP） |
| `tests/test_gdelt_monitor.py` | 新建 | 监控逻辑测试 |
| `tests/test_gdelt_api.py` | 新建 | API 端点测试 |

---

## 十三、实现优先级

1. **Phase 1（先做）：** `gdelt_client.py` + `gdelt_monitor.py`（poll + 去重 + emit） + `gdelt_event.py` + API + 测试
2. **Phase 2（后做）：** GDELT 2.0 Events CSV 解析 + CAMEO 编码映射 + 异常检测增强
3. **Phase 3（远期）：** GKG 接入 + 跨事件关联分析 + 趋势预测

Phase 1 的目标：专家订阅关键词 → GDELT 每 15 分钟拉取 → 发现新文章 → 推送通知 + 可选自动 ingest 到 AEGI pipeline。

---

_架构指导完成，待主人确认后出详细设计 / 实现提示词。_
