# GDELT 数据源接入实现提示词（给 Claude Code）

## 任务

基于 `docs/design/gdelt-integration-guide.md` 架构指导，实现 GDELT DOC API 数据源接入（Phase 1）。

**在开始编码前，先完整阅读以下文件：**
- `docs/design/gdelt-integration-guide.md` — 架构指导（主文档）
- `src/aegi_core/services/event_bus.py` — EventBus 实现
- `src/aegi_core/services/push_engine.py` — PushEngine
- `src/aegi_core/services/osint_collector.py` — OSINTCollector（GDELT 发现的 URL 可走这个流程深度采集）
- `src/aegi_core/db/models/collection_job.py` — CollectionJob 模型（复用做调度）
- `src/aegi_core/db/models/subscription.py` — Subscription 模型（复用做订阅匹配）
- `src/aegi_core/infra/searxng_client.py` — 参考 HTTP 客户端写法
- `src/aegi_core/settings.py` — Settings 类
- `src/aegi_core/api/routes/subscriptions.py` — 现有订阅路由（参考风格）
- `src/aegi_core/db/models/__init__.py` — 模型导出

## 实现范围（Phase 1 Only）

只做 GDELT DOC API 接入，不做 Events CSV 解析、不做 CAMEO 编码映射、不做 GKG。

核心目标：专家订阅关键词 → GDELT 每 15 分钟拉取 → 发现新文章 → emit 事件 → 推送通知 + 可选自动 ingest。

## 实现顺序

### Step 1：Settings + 数据模型 + Migration

1. `settings.py` 新增 5 个配置项：
```python
gdelt_proxy: str = "http://127.0.0.1:7890"
gdelt_poll_interval_minutes: int = 15
gdelt_max_articles_per_query: int = 50
gdelt_auto_ingest: bool = False
gdelt_anomaly_goldstein_threshold: float = -7.0
```

2. 新建 `db/models/gdelt_event.py`：按架构指导的 `GdeltEvent` 模型。Phase 1 中 CAMEO 相关字段（cameo_code, cameo_root, goldstein_scale, actor1, actor2, actor1_country, actor2_country）全部 nullable，暂时不填充。重点字段：uid, gdelt_id(unique), title, url, source_domain, language, published_at, tone, geo_country, geo_name, status, matched_subscription_uids, raw_data, created_at。

3. 修改 `db/models/__init__.py`：导出 GdeltEvent。

4. 新建 Alembic migration。**不要写死 down_revision**，先运行 `alembic heads` 确认当前最新 revision，再用它作为 down_revision。（贝叶斯 ACH 之后可能有修复 migration，不一定是 `d4e5f6a7b8c9`。）

### Step 2：GDELT DOC API 客户端

新建 `infra/gdelt_client.py`：

```python
@dataclass
class GDELTArticle:
    url: str
    title: str
    source_domain: str
    language: str
    seendate: str           # "20260211T153000Z"
    socialimage: str = ""
    tone: float = 0.0
    domain_country: str = ""

class GDELTClient:
    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, proxy: str | None = None) -> None:
        # 用 httpx.AsyncClient，如果 proxy 非空则配置代理
        ...

    async def search_articles(
        self,
        query: str,
        *,
        mode: str = "ArtList",
        timespan: str = "15min",
        max_records: int = 50,
        source_country: str | None = None,
        source_lang: str | None = None,
        sort: str = "DateDesc",
    ) -> list[GDELTArticle]:
        """调用 GDELT DOC API，返回文章列表。

        API URL 格式：
        {BASE_URL}?query={query}&mode={mode}&maxrecords={max_records}
        &timespan={timespan}&sort={sort}&format=json

        如果 source_country: query 加上 sourcecountry:{source_country}
        如果 source_lang: query 加上 sourcelang:{source_lang}

        响应 JSON 结构：
        {"articles": [{"url": "...", "title": "...", "seendate": "...",
                        "domain": "...", "language": "...", "socialimage": "...",
                        "tone": -1.23, "domaincountry": "US"}, ...]}

        注意：
        - GDELT 可能返回空 JSON 或无 articles 字段，要容错
        - 请求间隔至少 5 秒（在 monitor 层控制，client 不管）
        - 超时设 30 秒
        """

    async def close(self) -> None: ...
```

关键：proxy 参数从 `settings.gdelt_proxy` 传入。httpx 代理配置：`httpx.AsyncClient(proxy=proxy)` 。

### Step 3：GDELT Monitor 服务

新建 `services/gdelt_monitor.py`：

```python
class GDELTMonitor:
    def __init__(self, gdelt: GDELTClient, db_session: AsyncSession) -> None: ...

    async def poll(self) -> list[GdeltEvent]:
        """单次轮询：
        1. 加载所有 active Subscription，提取 match_rules 中的 keywords
           - Subscription.match_rules 是 JSONB，格式：{"keywords": ["伊朗", "核"], "countries": ["IR"]}
           - 如果 Subscription 的 event_types 包含 "gdelt.event_detected" 或为空（全匹配），则纳入
        2. 合并去重所有关键词
        3. 对每个关键词调 GDELTClient.search_articles()
           - 关键词之间间隔 5 秒（asyncio.sleep(5)），避免触发速率限制
        4. 对每篇文章：
           a. 计算 gdelt_id = sha256(url)[:32]
           b. 检查 gdelt_events 表是否已存在（去重）
           c. 匹配订阅：标题包含哪些订阅的关键词 → matched_subscription_uids
           d. 创建 GdeltEvent 行，status="new"
           e. emit "gdelt.event_detected" 事件
        5. 返回新发现的事件列表
        """

    async def ingest_event(self, event: GdeltEvent, case_uid: str) -> None:
        """将 GDELT 事件转为 AEGI Evidence + SourceClaim。
        Phase 1 简单实现（不做全文抓取和 LLM 提取，留给 Phase 2）：
        1. 用 event.title + event.url 作为 raw content，创建 Evidence 记录
        2. 创建一条 SourceClaim（quote = event.title，source_url = event.url）
        3. emit "claim.extracted" → 触发贝叶斯 ACH
        4. 更新 GdeltEvent.status = "ingested"

        如果创建失败，status = "error"，记录错误。
        Phase 2 再接入 OSINTCollector 抓全文 + LLM 提取多条 claim。
        """

    def _match_subscriptions(
        self, article: GDELTArticle, subscriptions: list[Subscription]
    ) -> list[str]:
        """返回匹配的 subscription uid 列表。
        匹配规则：
        - 关键词匹配：article.title 包含 subscription.match_rules.keywords 中任一词
        - 国家匹配：article.domain_country 在 subscription.match_rules.countries 中
        - 任一条件命中即匹配
        """
```

### Step 4：API 路由

新建 `api/routes/gdelt.py`：

```python
router = APIRouter(prefix="/gdelt", tags=["gdelt"])

# POST /gdelt/monitor/poll — 手动触发一次轮询（开发调试用）
# GET  /gdelt/events — 查询已发现的事件（分页：skip/limit，过滤：status/geo_country）
# GET  /gdelt/events/{uid} — 单个事件详情
# POST /gdelt/events/{uid}/ingest — 手动将事件转为 Evidence（需要 case_uid 参数）
# GET  /gdelt/stats — 统计：总事件数、按国家分布、按天分布
```

Phase 1 先不做 `/gdelt/monitor/start` 和 `/gdelt/monitor/stop`（定时调度 Phase 2 再做）。先做手动 poll 端点，能跑通整个链路。

修改 `api/main.py`：注册 gdelt router。

### Step 5：测试

1. `tests/test_gdelt_client.py`（mock HTTP 响应）：
   - `test_search_articles_success` — 正常返回文章列表
   - `test_search_articles_empty` — 空结果不报错
   - `test_search_articles_malformed_json` — 畸形 JSON 容错
   - `test_search_articles_timeout` — 超时容错
   - `test_search_articles_with_proxy` — 验证传入 proxy 参数后，内部 httpx.AsyncClient 的 proxy 配置不为空（不需要真的走代理请求，检查构造参数传递即可）

2. `tests/test_gdelt_monitor.py`（mock GDELTClient + test DB）：
   - `test_poll_discovers_new_events` — 发现新文章 → 写入 DB + emit 事件
   - `test_poll_deduplicates` — 同一 URL 不重复写入
   - `test_poll_matches_subscriptions` — 正确匹配订阅关键词
   - `test_poll_no_subscriptions_skips` — 无订阅时不调 API
   - `test_ingest_event_emits_claim_extracted` — ingest 后 emit claim.extracted

3. `tests/test_gdelt_api.py`（mock 依赖）：
   - `test_manual_poll` — POST /gdelt/monitor/poll 返回发现的事件
   - `test_list_events` — GET /gdelt/events 分页查询
   - `test_get_event_detail` — GET /gdelt/events/{uid}
   - `test_ingest_event` — POST /gdelt/events/{uid}/ingest
   - `test_stats` — GET /gdelt/stats 返回统计

## 关键约束

- **不修改现有代码的行为**：GDELT 是纯增量模块，不动现有的 OSINT、EventBus、Subscription 等
- **不引入新依赖**：只用 httpx（已有）、sqlalchemy（已有）
- **代理必须配置**：国内服务器访问 GDELT 需要走代理，`GDELTClient.__init__` 必须支持 proxy 参数
- **容错优先**：GDELT API 不稳定，所有 HTTP 调用必须 try/except，失败记日志不崩溃
- **去重必须可靠**：gdelt_id = sha256(url)[:32]，unique 约束，重复插入跳过不报错
- **uid 生成**：遵循项目现有模式（uuid4().hex）
- **测试不依赖外部服务**：mock HTTP、mock DB、不真的调 GDELT API
- **现有测试不能 break**：实现完成后跑全量 pytest，确保 0 failed

## 验收标准

1. `pytest tests/test_gdelt_client.py tests/test_gdelt_monitor.py tests/test_gdelt_api.py` 全绿
2. `pytest` 全量测试 0 failed（包括之前的 333 个）
3. `alembic upgrade head` 成功
4. 手动 curl `POST /gdelt/monitor/poll` 能返回结果（如果有网络代理的话）
