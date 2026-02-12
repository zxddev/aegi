# GDELT Phase 2：Events CSV 解析 + CAMEO 编码 + 异常检测（给 Claude Code）

## 任务

在 GDELT Phase 1（DOC API 文章搜索）基础上，接入 GDELT 2.0 Events CSV 数据，填充 CAMEO 编码字段，并实现基于 Goldstein Scale 的异常检测。

**在开始编码前，先完整阅读以下文件：**
- `docs/design/gdelt-integration-guide.md` — 架构指导（重点看 CAMEO 编码体系、异常检测部分）
- `src/aegi_core/infra/gdelt_client.py` — 现有 GDELTClient（Phase 1 DOC API）
- `src/aegi_core/services/gdelt_monitor.py` — 现有 GDELTMonitor
- `src/aegi_core/db/models/gdelt_event.py` — GdeltEvent 模型（CAMEO 字段已预留，全 nullable）
- `src/aegi_core/settings.py` — Settings
- `src/aegi_core/services/event_bus.py` — EventBus

## 背景知识

### GDELT 2.0 Events CSV

GDELT 每 15 分钟发布一个 CSV 文件，包含全球结构化事件记录。

下载地址：`http://data.gdeltproject.org/gdeltv2/lastupdate.txt`
该文件包含 3 行，第一行是最新的 Events CSV 的 URL，格式如：
```
http://data.gdeltproject.org/gdeltv2/20260212114500.export.CSV.zip
```

CSV 字段（58 列），核心字段：
| 列号 | 字段名 | 说明 |
|------|--------|------|
| 0 | GLOBALEVENTID | 全局事件 ID |
| 5 | Actor1Code | 行为者1 CAMEO 编码 |
| 6 | Actor1Name | 行为者1 名称 |
| 7 | Actor1CountryCode | 行为者1 国家 |
| 15 | Actor2Code | 行为者2 CAMEO 编码 |
| 16 | Actor2Name | 行为者2 名称 |
| 17 | Actor2CountryCode | 行为者2 国家 |
| 26 | EventCode | CAMEO 事件编码（如 "0211" = 呼吁合作） |
| 27 | EventBaseCode | CAMEO 基础编码（如 "021"） |
| 28 | EventRootCode | CAMEO 根编码（如 "02" = 呼吁） |
| 30 | GoldsteinScale | Goldstein 冲突/合作分数（-10 到 +10） |
| 33 | AvgTone | 平均基调分数 |
| 34 | Actor1Geo_Type | 地理类型 |
| 39 | Actor1Geo_Lat | 纬度 |
| 40 | Actor1Geo_Long | 经度 |
| 53 | SOURCEURL | 来源 URL |
| 57 | DATEADDED | 添加日期 |

### CAMEO 编码体系

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

## 实现顺序

### Step 1：CAMEO 编码映射表

新建 `infra/cameo.py`：

```python
"""CAMEO 事件编码映射。"""

# 根编码 → 中文描述
CAMEO_ROOT_LABELS: dict[str, str] = {
    "01": "公开声明",
    "02": "呼吁",
    "03": "表达合作意向",
    "04": "咨询",
    "05": "外交合作",
    "06": "物质合作",
    "07": "提供援助",
    "08": "让步",
    "09": "调查",
    "10": "要求",
    "11": "拒绝",
    "12": "威胁",
    "13": "抗议",
    "14": "暴力行为",
    "15": "使用武力",
    "17": "军事行动",
    "18": "胁迫",
    "19": "大规模暴力",
    "20": "大规模杀伤",
}

# 根编码 → 冲突/合作分类
CAMEO_CATEGORY: dict[str, str] = {
    "01": "neutral",
    "02": "cooperation",
    "03": "cooperation",
    "04": "cooperation",
    "05": "cooperation",
    "06": "cooperation",
    "07": "cooperation",
    "08": "cooperation",
    "09": "neutral",
    "10": "neutral",
    "11": "conflict",
    "12": "conflict",
    "13": "conflict",
    "14": "conflict",
    "15": "conflict",
    "17": "conflict",
    "18": "conflict",
    "19": "conflict",
    "20": "conflict",
}

def cameo_root_label(root_code: str) -> str:
    """返回 CAMEO 根编码的中文描述。"""
    return CAMEO_ROOT_LABELS.get(root_code, f"未知({root_code})")

def cameo_category(root_code: str) -> str:
    """返回 CAMEO 根编码的分类：cooperation / conflict / neutral。"""
    return CAMEO_CATEGORY.get(root_code, "unknown")

def is_high_conflict(root_code: str) -> bool:
    """是否为高冲突事件（14-20）。"""
    try:
        return int(root_code) >= 14
    except (ValueError, TypeError):
        return False
```

### Step 2：GDELTClient 新增 Events CSV 方法

在 `infra/gdelt_client.py` 中新增：

```python
@dataclass
class GDELTEvent:
    """GDELT 2.0 Events CSV 解析后的结构化事件。"""
    global_event_id: str
    actor1_code: str = ""
    actor1_name: str = ""
    actor1_country: str = ""
    actor2_code: str = ""
    actor2_name: str = ""
    actor2_country: str = ""
    event_code: str = ""          # 完整 CAMEO 编码
    event_base_code: str = ""     # 基础编码
    event_root_code: str = ""     # 根编码（2位）
    goldstein_scale: float = 0.0
    avg_tone: float = 0.0
    geo_lat: float | None = None
    geo_lon: float | None = None
    geo_country: str = ""
    geo_name: str = ""
    source_url: str = ""
    date_added: str = ""

class GDELTClient:
    # ... 现有方法保留 ...

    async def fetch_latest_events(
        self,
        *,
        max_events: int = 500,
        country_filter: set[str] | None = None,
        cameo_root_filter: set[str] | None = None,
        min_goldstein: float | None = None,
        max_goldstein: float | None = None,
    ) -> list[GDELTEvent]:
        """下载并解析最新的 GDELT 2.0 Events CSV。

        流程：
        1. GET http://data.gdeltproject.org/gdeltv2/lastupdate.txt
        2. 解析第一行获取 CSV zip URL
        3. 下载 zip（走代理）
        4. 解压，逐行解析 CSV（tab 分隔，无 header）
        5. 按 country_filter / cameo_root_filter / goldstein 范围过滤
        6. 返回 GDELTEvent 列表

        注意：
        - CSV 是 tab 分隔，不是逗号
        - 没有 header 行，按列号索引
        - 字段可能为空，要容错
        - zip 文件可能几 MB，用 io.BytesIO 在内存中处理
        - 超时 60 秒
        """

    async def fetch_events_by_timerange(
        self,
        start: str,  # "20260212" 格式
        end: str,
        **filters,
    ) -> list[GDELTEvent]:
        """下载指定时间范围的 Events CSV。

        GDELT 历史文件 URL 格式：
        http://data.gdeltproject.org/gdeltv2/{YYYYMMDDHHMMSS}.export.CSV.zip

        每 15 分钟一个文件。遍历时间范围内的所有文件。
        Phase 2 先只实现 fetch_latest_events（最新一个文件），
        这个方法做骨架，后续补充。
        """
        raise NotImplementedError("Phase 3: 历史数据回溯")
```

### Step 3：GDELTMonitor 增强

在 `services/gdelt_monitor.py` 中新增：

```python
async def poll_events(self) -> list[GdeltEvent]:
    """轮询 GDELT Events CSV（与 poll() 的 DOC API 互补）。

    流程：
    1. 调用 GDELTClient.fetch_latest_events()
    2. 按订阅的 match_rules 过滤：
       - countries: actor1_country 或 actor2_country 匹配
       - cameo_roots: event_root_code 匹配
       - keywords: 暂不支持（Events CSV 没有标题文本）
    3. 去重（gdelt_id = global_event_id）
    4. 填充 GdeltEvent 的 CAMEO 字段：
       cameo_code=event.event_code,
       cameo_root=event.event_root_code,
       goldstein_scale=event.goldstein_scale,
       actor1=event.actor1_name,
       actor2=event.actor2_name,
       actor1_country=event.actor1_country,
       actor2_country=event.actor2_country,
    5. 持久化 + emit "gdelt.event_detected"
    6. 运行异常检测
    """

async def detect_anomalies(self, events: list[GdeltEvent]) -> list[GdeltEvent]:
    """检测异常事件并 emit 高优先级告警。

    规则 1：Goldstein Scale 极端值
    - goldstein_scale < settings.gdelt_anomaly_goldstein_threshold（默认 -7.0）
    - 表示严重冲突事件

    规则 2：同一地区事件突增
    - 查询该 geo_country 最近 24 小时的事件数
    - 查询该 geo_country 过去 7 天的日均事件数
    - 如果最近 24h > 日均 × 3，标记为异常

    规则 3：高冲突 CAMEO 编码
    - cameo_root in ("14", "15", "17", "18", "19", "20")
    - 且 goldstein_scale < -5

    对每个异常事件：
    emit AegiEvent(
        event_type="gdelt.anomaly_detected",
        severity="high",
        payload={
            "anomaly_type": "extreme_conflict" | "event_surge" | "high_conflict_cameo",
            "title": event.title or f"{event.actor1} → {event.actor2}",
            "goldstein_scale": event.goldstein_scale,
            "cameo_code": event.cameo_code,
            "cameo_label": cameo_root_label(event.cameo_root),
            "geo_country": event.geo_country,
            "source_url": event.url,
        },
    )

    返回异常事件列表。
    """
```

### Step 4：调度器集成

修改 `services/gdelt_scheduler.py` 的 `_loop` 方法，在 DOC API poll 之后也调用 Events CSV poll：

```python
# 现有的 DOC API 轮询
new_articles = await self._monitor.poll()

# 新增：Events CSV 轮询
try:
    new_events = await self._monitor.poll_events()
    logger.info("GDELT Events CSV poll: %d new events", len(new_events))
except Exception:
    logger.exception("GDELT Events CSV poll failed")
```

### Step 5：API 增强

在 `api/routes/gdelt.py` 中新增/修改：

```python
# GET /gdelt/events 增加过滤参数：
#   cameo_root: str | None — 按 CAMEO 根编码过滤
#   min_goldstein: float | None — Goldstein 下限
#   max_goldstein: float | None — Goldstein 上限
#   actor_country: str | None — 按行为者国家过滤

# GET /gdelt/events/{uid} 响应中增加 CAMEO 描述：
#   cameo_label: str — CAMEO 根编码的中文描述
#   cameo_category: str — cooperation / conflict / neutral

# GET /gdelt/stats 增加：
#   cameo_distribution: dict[str, int] — 按 CAMEO 根编码统计
#   conflict_cooperation_ratio: float — 冲突/合作事件比例
#   anomaly_count: int — 异常事件数

# GET /gdelt/anomalies — 新端点，返回最近的异常事件列表
```

### Step 6：测试

1. `tests/test_cameo.py`：
   - `test_root_label` — 所有根编码返回正确中文描述
   - `test_category` — cooperation/conflict/neutral 分类正确
   - `test_is_high_conflict` — 14-20 返回 True，其他 False
   - `test_unknown_code` — 未知编码不报错

2. `tests/test_gdelt_events_csv.py`（mock HTTP）：
   - `test_fetch_latest_events_success` — 构造 mock CSV zip，验证解析正确
   - `test_fetch_latest_events_with_filters` — country_filter 和 cameo_root_filter 生效
   - `test_fetch_latest_events_empty` — 空 CSV 不报错
   - `test_fetch_latest_events_malformed` — 畸形行跳过不崩溃
   - `test_csv_tab_separated` — 确认 tab 分隔解析正确

3. `tests/test_gdelt_anomaly.py`（mock DB）：
   - `test_detect_extreme_goldstein` — goldstein < -7 触发异常
   - `test_detect_event_surge` — 事件突增触发异常
   - `test_detect_high_conflict_cameo` — 高冲突 CAMEO + 低 goldstein 触发
   - `test_no_anomaly_normal_events` — 正常事件不触发
   - `test_anomaly_emits_event` — 异常检测 emit "gdelt.anomaly_detected"

4. 构造测试用 CSV 数据：

```python
def _make_test_csv_row(**overrides) -> str:
    """构造一行 GDELT Events CSV（58 列 tab 分隔）。"""
    defaults = [""] * 58
    defaults[0] = overrides.get("global_event_id", "123456789")
    defaults[5] = overrides.get("actor1_code", "USA")
    defaults[6] = overrides.get("actor1_name", "UNITED STATES")
    defaults[7] = overrides.get("actor1_country", "US")
    defaults[15] = overrides.get("actor2_code", "IRN")
    defaults[16] = overrides.get("actor2_name", "IRAN")
    defaults[17] = overrides.get("actor2_country", "IR")
    defaults[26] = overrides.get("event_code", "0211")
    defaults[27] = overrides.get("event_base_code", "021")
    defaults[28] = overrides.get("event_root_code", "02")
    defaults[30] = str(overrides.get("goldstein_scale", 3.0))
    defaults[33] = str(overrides.get("avg_tone", -1.5))
    defaults[53] = overrides.get("source_url", "https://example.com/news")
    defaults[57] = overrides.get("date_added", "20260212120000")
    return "\t".join(defaults)
```

## 关键约束

- **不修改 GdeltEvent 模型**：CAMEO 字段已预留，只需填充
- **不修改 Phase 1 的 poll() 方法**：poll_events() 是新增方法，与 poll() 并行
- **CSV 解析要容错**：GDELT CSV 经常有畸形行，跳过不崩溃
- **内存处理 zip**：不写临时文件，用 io.BytesIO
- **代理必须配置**：下载 CSV 也需要走代理
- **测试不依赖外部服务**：mock HTTP 响应，构造 CSV 数据
- **现有测试不能 break**

## 验收标准

1. `pytest tests/test_cameo.py tests/test_gdelt_events_csv.py tests/test_gdelt_anomaly.py` 全绿
2. 全量 `pytest` 0 failed
3. `POST /gdelt/monitor/poll` 后，新事件的 CAMEO 字段有值（如果走了 Events CSV）
4. Goldstein < -7 的事件触发 `gdelt.anomaly_detected` 事件
5. `GET /gdelt/stats` 返回 CAMEO 分布统计
