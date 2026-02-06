"""RSSHub 推送采集适配器。

RSSHub 是一个开源的 RSS 生成器，可以将各种网站内容转换为 RSS 订阅。
此适配器提供与 RSSHub 的集成，用于情报推送采集。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RSSHubConfig:
    """RSSHub 配置。"""

    base_url: str  # RSSHub 服务地址
    access_key: str | None = None  # 可选的访问密钥
    timeout_seconds: int = 30
    verify_ssl: bool = True


@dataclass
class FeedItem:
    """RSS 订阅项。"""

    title: str
    link: str
    description: str
    published_at: datetime
    guid: str
    author: str | None = None
    categories: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Feed:
    """RSS 订阅源。"""

    title: str
    link: str
    description: str
    items: list[FeedItem]
    last_build_date: datetime | None = None
    language: str = "zh-CN"
    metadata: dict[str, Any] = field(default_factory=dict)


class RSSHubClient:
    """RSSHub 客户端。"""

    def __init__(self, config: RSSHubConfig) -> None:
        """初始化客户端。

        Args:
            config: RSSHub 配置
        """
        self._config = config

    async def get_feed(self, route: str) -> Feed:
        """获取 RSS 订阅。

        Args:
            route: RSSHub 路由（例如 "/twitter/user/elonmusk"）

        Returns:
            RSS 订阅源
        """
        url = f"{self._config.base_url}{route}"
        params = {}
        if self._config.access_key:
            params["key"] = self._config.access_key

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            verify=self._config.verify_ssl,
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return self._parse_rss(response.text)

    async def get_feed_json(self, route: str) -> dict[str, Any]:
        """获取 JSON 格式的订阅。

        Args:
            route: RSSHub 路由

        Returns:
            JSON 格式的订阅数据
        """
        # 添加 .json 后缀获取 JSON 格式
        url = f"{self._config.base_url}{route}.json"
        params = {}
        if self._config.access_key:
            params["key"] = self._config.access_key

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            verify=self._config.verify_ssl,
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    def _parse_rss(self, xml_content: str) -> Feed:
        """解析 RSS XML。"""
        root = ElementTree.fromstring(xml_content)
        channel = root.find("channel")
        if channel is None:
            raise ValueError("无效的 RSS 格式：缺少 channel 元素")

        # 解析频道信息
        title = self._get_text(channel, "title", "") or ""
        link = self._get_text(channel, "link", "") or ""
        description = self._get_text(channel, "description", "") or ""
        language = self._get_text(channel, "language", "zh-CN") or "zh-CN"

        # 解析最后构建日期
        last_build_str = self._get_text(channel, "lastBuildDate", "")
        last_build_date = self._parse_date(last_build_str) if last_build_str else None

        # 解析订阅项
        items: list[FeedItem] = []
        for item_elem in channel.findall("item"):
            items.append(self._parse_item(item_elem))

        return Feed(
            title=title,
            link=link,
            description=description,
            items=items,
            last_build_date=last_build_date,
            language=language,
        )

    def _parse_item(self, item_elem: ElementTree.Element) -> FeedItem:
        """解析单个订阅项。"""
        title = self._get_text(item_elem, "title", "") or ""
        link = self._get_text(item_elem, "link", "") or ""
        description = self._get_text(item_elem, "description", "") or ""
        guid = self._get_text(item_elem, "guid", link) or link
        author = self._get_text(item_elem, "author", None)

        # 解析发布日期
        pub_date_str = self._get_text(item_elem, "pubDate", "")
        published_at = (
            self._parse_date(pub_date_str) if pub_date_str else datetime.now(UTC)
        )

        # 解析分类
        categories = [cat.text for cat in item_elem.findall("category") if cat.text]

        return FeedItem(
            title=title,
            link=link,
            description=description,
            published_at=published_at,
            guid=guid,
            author=author,
            categories=categories,
        )

    def _get_text(
        self, elem: ElementTree.Element, tag: str, default: str | None
    ) -> str | None:
        """获取子元素文本。"""
        child = elem.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return default

    def _parse_date(self, date_str: str) -> datetime:
        """解析日期字符串。"""
        # RFC 822 格式
        from email.utils import parsedate_to_datetime

        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            # 尝试 ISO 格式
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                return datetime.now(UTC)


# 预定义的常用路由
class RSSHubRoutes:
    """常用 RSSHub 路由。"""

    # 新闻
    BBC_WORLD = "/bbc/world"
    BBC_CHINA = "/bbc/chinese/world"
    REUTERS = "/reuters/world"
    AP_NEWS = "/apnews/topics/apf-topnews"

    # 军事/防务
    DEFENSE_NEWS = "/defensenews"
    JANES = "/janes"
    NAVY_TIMES = "/navytimes"

    # 政府
    US_DOD = "/dod/news"
    US_STATE_DEPT = "/state"

    # 智库
    CSIS = "/csis"
    RAND = "/rand"
    BROOKINGS = "/brookings"

    # 社交媒体（需要配置）
    @staticmethod
    def twitter_user(username: str) -> str:
        """Twitter 用户时间线。"""
        return f"/twitter/user/{username}"

    @staticmethod
    def telegram_channel(channel: str) -> str:
        """Telegram 频道。"""
        return f"/telegram/channel/{channel}"


class RSSHubCollector:
    """RSSHub 情报采集器。"""

    def __init__(self, client: RSSHubClient) -> None:
        """初始化采集器。

        Args:
            client: RSSHub 客户端
        """
        self._client = client
        self._subscriptions: list[str] = []

    def add_subscription(self, route: str) -> None:
        """添加订阅。"""
        if route not in self._subscriptions:
            self._subscriptions.append(route)

    def remove_subscription(self, route: str) -> None:
        """移除订阅。"""
        if route in self._subscriptions:
            self._subscriptions.remove(route)

    async def collect_all(self) -> list[Feed]:
        """采集所有订阅。"""
        feeds: list[Feed] = []
        for route in self._subscriptions:
            try:
                feed = await self._client.get_feed(route)
                feeds.append(feed)
            except Exception as e:
                logger.warning("采集失败 [%s]: %s", route, e)
        return feeds

    async def collect_since(
        self,
        since: datetime,
    ) -> list[FeedItem]:
        """采集指定时间后的新条目。

        Args:
            since: 起始时间

        Returns:
            新条目列表
        """
        new_items: list[FeedItem] = []
        feeds = await self.collect_all()
        for feed in feeds:
            for item in feed.items:
                if item.published_at > since:
                    new_items.append(item)
        # 按发布时间排序
        new_items.sort(key=lambda x: x.published_at, reverse=True)
        return new_items


async def fetch_rss_items(feed_url: str, *, timeout: int = 30) -> list[dict[str, Any]]:
    """获取 RSS 条目列表。"""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(feed_url)
        response.raise_for_status()

    parser = RSSHubClient(RSSHubConfig(base_url="", timeout_seconds=timeout))
    feed = parser._parse_rss(response.text)

    items: list[dict[str, Any]] = []
    for item in feed.items:
        content = item.description or ""
        content_hash = sha256(content.encode("utf-8")).hexdigest() if content else ""
        items.append(
            {
                "title": item.title,
                "link": item.link,
                "content": content,
                "source": feed_url,
                "hash": content_hash,
                "published_at": item.published_at.isoformat(),
                "author": item.author,
                "categories": item.categories,
            }
        )
    return items
