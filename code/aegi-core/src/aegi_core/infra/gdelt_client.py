# Author: msq
"""GDELT 客户端。

- DOC API：按关键词检索文章（Phase 1）
- Events CSV：下载/解析结构化事件（Phase 2）
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import zipfile
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


def _safe_get(row: list[str], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return row[index].strip()


def _to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value.strip()) if value else default
    except (TypeError, ValueError, AttributeError):
        return default


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


@dataclass
class GDELTArticle:
    """GDELT DOC API 返回的单篇文章。"""

    url: str = ""
    title: str = ""
    source_domain: str = ""
    language: str = ""
    seendate: str = ""
    socialimage: str = ""
    tone: float = 0.0
    domain_country: str = ""


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
    event_code: str = ""
    event_base_code: str = ""
    event_root_code: str = ""
    goldstein_scale: float = 0.0
    avg_tone: float = 0.0
    geo_lat: float | None = None
    geo_lon: float | None = None
    geo_country: str = ""
    geo_name: str = ""
    source_url: str = ""
    date_added: str = ""


class GDELTClient:
    """GDELT API 异步客户端，遵循 SearXNGClient 模式。"""

    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
    EVENTS_LAST_UPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _build_query(
        query: str,
        *,
        source_country: str | None,
        source_lang: str | None,
    ) -> str:
        """构建 GDELT query，避免无效写法（如 '* sourcecountry:IR'）。"""
        parts: list[str] = []
        normalized_query = query.strip()
        if normalized_query and normalized_query != "*":
            parts.append(normalized_query)

        if source_country:
            country = source_country.strip().upper()
            if country:
                parts.append(f"sourcecountry:{country}")

        if source_lang:
            lang = source_lang.strip()
            if lang:
                parts.append(f"sourcelang:{lang}")

        # GDELT query 不能为空；无业务关键词时给一个稳定兜底词。
        if not parts:
            parts.append("news")

        return " ".join(parts)

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                proxy=self._proxy,
            )
        return self._client

    async def search_articles(
        self,
        query: str,
        *,
        mode: str = "ArtList",
        timespan: str = "1d",
        max_records: int = 50,
        source_country: str | None = None,
        source_lang: str | None = None,
        sort: str = "DateDesc",
    ) -> list[GDELTArticle]:
        """搜索 GDELT 文章，容错返回空列表。"""
        built_query = self._build_query(
            query,
            source_country=source_country,
            source_lang=source_lang,
        )

        params = {
            "query": built_query,
            "mode": mode,
            "maxrecords": str(max_records),
            "timespan": timespan,
            "sort": sort,
            "format": "json",
        }

        client = await self._ensure_client()
        try:
            resp: httpx.Response | None = None
            for attempt in range(3):
                resp = await client.get(self.BASE_URL, params=params)
                if resp.status_code != 429:
                    break
                if attempt >= 2:
                    break
                wait_seconds = 5 * (attempt + 1)
                logger.warning(
                    "GDELT API 限流，重试: attempt=%d wait=%ds query=%s",
                    attempt + 1,
                    wait_seconds,
                    built_query,
                )
                await asyncio.sleep(wait_seconds)

            if resp is None:
                return []
            if resp.status_code != 200:
                logger.warning(
                    "GDELT API 非 200: status=%d query=%s",
                    resp.status_code,
                    built_query,
                )
                return []

            content_type = (resp.headers.get("content-type") or "").lower()
            body_text = resp.text
            if "json" not in content_type:
                if (
                    "timespan is too short" in body_text.lower()
                    and timespan != "1d"
                ):
                    logger.warning(
                        "GDELT timespan 过短，自动回退到 1d: query=%s timespan=%s",
                        built_query,
                        timespan,
                    )
                    return await self.search_articles(
                        query=query,
                        mode=mode,
                        timespan="1d",
                        max_records=max_records,
                        source_country=source_country,
                        source_lang=source_lang,
                        sort=sort,
                    )
                logger.warning(
                    "GDELT API 返回非 JSON: ctype=%s query=%s body_head=%s",
                    content_type,
                    built_query,
                    body_text[:160].replace("\n", " "),
                )
                return []

            data = resp.json()
        except httpx.TimeoutException:
            logger.warning("GDELT API 超时: query=%s", built_query)
            return []
        except Exception as exc:
            logger.warning("GDELT API 请求失败: query=%s err=%s", built_query, exc)
            return []

        raw_articles = data.get("articles", [])
        if not isinstance(raw_articles, list):
            logger.warning("GDELT API 返回非预期格式: %s", type(raw_articles))
            return []

        articles: list[GDELTArticle] = []
        for item in raw_articles[:max_records]:
            try:
                articles.append(
                    GDELTArticle(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        source_domain=item.get("domain", ""),
                        language=item.get("language", ""),
                        seendate=item.get("seendate", ""),
                        socialimage=item.get("socialimage", ""),
                        tone=float(item.get("tone", 0.0)),
                        domain_country=item.get("domaincountry", "")
                        or item.get("sourcecountry", ""),
                    )
                )
            except (ValueError, TypeError):
                continue
        return articles

    def _extract_latest_events_url(self, content: str) -> str | None:
        for line in content.splitlines():
            line = line.strip()
            if not line or ".export.CSV.zip" not in line:
                continue
            if line.startswith("http://") or line.startswith("https://"):
                return line
            for part in line.split():
                part = part.strip()
                if not part:
                    continue
                if part.startswith("http://") or part.startswith("https://"):
                    if ".export.CSV.zip" in part:
                        return part
                elif part.endswith(".export.CSV.zip"):
                    return f"http://data.gdeltproject.org/gdeltv2/{part.split('/')[-1]}"
        return None

    def _parse_event_row(self, row: list[str]) -> GDELTEvent | None:
        if len(row) < 31:
            return None
        global_event_id = _safe_get(row, 0)
        if not global_event_id:
            return None

        actor1_country = _safe_get(row, 7).upper()
        actor2_country = _safe_get(row, 17).upper()
        avg_tone = _to_float(
            _safe_get(row, 33), default=_to_float(_safe_get(row, 34), 0.0)
        )

        source_url = _safe_get(row, 53)
        if not source_url.startswith("http"):
            fallback_source = _safe_get(row, 57)
            if fallback_source.startswith("http"):
                source_url = fallback_source

        date_added = _safe_get(row, 57) or _safe_get(row, 56)

        geo_country = _first_non_empty(
            _safe_get(row, 37).upper(),
            _safe_get(row, 44).upper(),
            _safe_get(row, 51).upper(),
            actor1_country,
            actor2_country,
        )
        geo_name = _first_non_empty(
            _safe_get(row, 36), _safe_get(row, 43), _safe_get(row, 49)
        )

        geo_lat = _to_float(_safe_get(row, 39), default=float("nan"))
        geo_lon = _to_float(_safe_get(row, 40), default=float("nan"))

        return GDELTEvent(
            global_event_id=global_event_id,
            actor1_code=_safe_get(row, 5),
            actor1_name=_safe_get(row, 6),
            actor1_country=actor1_country,
            actor2_code=_safe_get(row, 15),
            actor2_name=_safe_get(row, 16),
            actor2_country=actor2_country,
            event_code=_safe_get(row, 26),
            event_base_code=_safe_get(row, 27),
            event_root_code=_safe_get(row, 28),
            goldstein_scale=_to_float(_safe_get(row, 30), default=0.0),
            avg_tone=avg_tone,
            geo_lat=None if geo_lat != geo_lat else geo_lat,
            geo_lon=None if geo_lon != geo_lon else geo_lon,
            geo_country=geo_country,
            geo_name=geo_name,
            source_url=source_url,
            date_added=date_added,
        )

    def _match_event_filters(
        self,
        event: GDELTEvent,
        *,
        country_filter: set[str] | None,
        cameo_root_filter: set[str] | None,
        min_goldstein: float | None,
        max_goldstein: float | None,
    ) -> bool:
        if country_filter:
            event_countries = {
                event.actor1_country.upper(),
                event.actor2_country.upper(),
                event.geo_country.upper(),
            }
            if not event_countries.intersection(country_filter):
                return False

        if cameo_root_filter and event.event_root_code not in cameo_root_filter:
            return False

        if min_goldstein is not None and event.goldstein_scale < min_goldstein:
            return False
        if max_goldstein is not None and event.goldstein_scale > max_goldstein:
            return False

        return True

    def _parse_events_zip(
        self,
        csv_zip_bytes: bytes,
        *,
        max_events: int,
        country_filter: set[str] | None,
        cameo_root_filter: set[str] | None,
        min_goldstein: float | None,
        max_goldstein: float | None,
    ) -> list[GDELTEvent]:
        try:
            with zipfile.ZipFile(io.BytesIO(csv_zip_bytes)) as zf:
                csv_files = [
                    name for name in zf.namelist() if name.lower().endswith(".csv")
                ]
                if not csv_files:
                    logger.warning("GDELT Events ZIP 中未找到 CSV 文件")
                    return []
                with zf.open(csv_files[0], "r") as csv_fp:
                    raw_bytes = csv_fp.read()
        except zipfile.BadZipFile:
            logger.warning("GDELT Events ZIP 格式错误")
            return []
        except Exception as exc:
            logger.warning("GDELT Events ZIP 读取失败: %s", exc)
            return []

        text: str
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_bytes.decode("latin-1", errors="ignore")

        events: list[GDELTEvent] = []
        reader = csv.reader(io.StringIO(text), delimiter="\t")
        for row in reader:
            if not row:
                continue
            event = self._parse_event_row(row)
            if event is None:
                continue
            if not self._match_event_filters(
                event,
                country_filter=country_filter,
                cameo_root_filter=cameo_root_filter,
                min_goldstein=min_goldstein,
                max_goldstein=max_goldstein,
            ):
                continue
            events.append(event)
            if len(events) >= max_events:
                break
        return events

    async def fetch_latest_events(
        self,
        *,
        max_events: int = 500,
        country_filter: set[str] | None = None,
        cameo_root_filter: set[str] | None = None,
        min_goldstein: float | None = None,
        max_goldstein: float | None = None,
    ) -> list[GDELTEvent]:
        """下载并解析最新的 GDELT 2.0 Events CSV。"""
        client = await self._ensure_client()

        norm_country_filter = {
            c.strip().upper() for c in (country_filter or set()) if c.strip()
        }
        norm_cameo_filter = {
            c.strip() for c in (cameo_root_filter or set()) if c.strip()
        }

        try:
            update_resp = await client.get(self.EVENTS_LAST_UPDATE_URL, timeout=60.0)
            if update_resp.status_code != 200:
                logger.warning(
                    "GDELT lastupdate 非 200: status=%d", update_resp.status_code
                )
                return []
            latest_url = self._extract_latest_events_url(update_resp.text)
            if not latest_url:
                logger.warning("GDELT lastupdate 未解析出 Events URL")
                return []

            csv_resp = await client.get(latest_url, timeout=60.0)
            if csv_resp.status_code != 200:
                logger.warning(
                    "GDELT Events CSV 下载失败: status=%d", csv_resp.status_code
                )
                return []

            return self._parse_events_zip(
                csv_resp.content,
                max_events=max_events,
                country_filter=norm_country_filter or None,
                cameo_root_filter=norm_cameo_filter or None,
                min_goldstein=min_goldstein,
                max_goldstein=max_goldstein,
            )
        except httpx.TimeoutException:
            logger.warning("GDELT Events CSV 下载超时")
            return []
        except Exception as exc:
            logger.warning("GDELT Events CSV 拉取失败: %s", exc)
            return []

    async def fetch_events_by_timerange(
        self,
        start: str,
        end: str,
        **filters,
    ) -> list[GDELTEvent]:
        """下载指定时间范围的 Events CSV（Phase 3）。"""
        raise NotImplementedError("Phase 3: 历史数据回溯")

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
