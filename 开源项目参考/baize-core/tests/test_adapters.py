"""适配器测试。"""

from __future__ import annotations

import pytest

from baize_core.adapters.kafka_adapter import (
    Event,
    KafkaConfig,
    KafkaEventPublisher,
    KafkaTopics,
)
from baize_core.adapters.perplexica import (
    PerplexicaClient,
    PerplexicaConfig,
)
from baize_core.adapters.rsshub import (
    RSSHubClient,
    RSSHubConfig,
    RSSHubRoutes,
)


class TestEvent:
    """Event 测试。"""

    def test_to_json(self) -> None:
        """测试序列化。"""
        event = Event(
            event_id="evt_1",
            event_type="test",
            payload={"key": "value"},
        )
        json_str = event.to_json()
        assert "evt_1" in json_str
        assert "test" in json_str

    def test_from_json(self) -> None:
        """测试反序列化。"""
        json_str = '{"event_id": "evt_1", "event_type": "test", "payload": {"key": "value"}, "timestamp": "2024-01-01T00:00:00+00:00", "metadata": {}}'
        event = Event.from_json(json_str)
        assert event.event_id == "evt_1"
        assert event.event_type == "test"
        assert event.payload == {"key": "value"}


class TestKafkaEventPublisher:
    """KafkaEventPublisher 测试。"""

    @pytest.mark.asyncio
    async def test_publish_without_connection(self) -> None:
        """测试未连接时发布（模拟模式）。"""
        config = KafkaConfig(bootstrap_servers="localhost:9092")
        publisher = KafkaEventPublisher(config)
        event = Event(
            event_id="evt_1",
            event_type="test",
            payload={},
        )
        # 不应抛出异常
        await publisher.publish("test_topic", event)


class TestPerplexicaClient:
    """PerplexicaClient 测试。"""

    @pytest.mark.asyncio
    async def test_parse_response(self) -> None:
        """测试响应解析。"""
        config = PerplexicaConfig(base_url="http://localhost:3000")
        client = PerplexicaClient(config)
        data = {
            "message": "AI 生成的答案",
            "sources": [
                {"title": "来源1", "url": "http://example.com", "content": "摘要1"},
            ],
        }
        response = client._parse_response("测试查询", data, 100)
        assert response.query == "测试查询"
        assert response.answer == "AI 生成的答案"
        assert len(response.sources) == 1
        assert response.sources[0].title == "来源1"


class TestRSSHubClient:
    """RSSHubClient 测试。"""

    def test_parse_rss(self) -> None:
        """测试 RSS 解析。"""
        config = RSSHubConfig(base_url="http://localhost:1200")
        client = RSSHubClient(config)
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>测试订阅</title>
    <link>http://example.com</link>
    <description>测试描述</description>
    <item>
      <title>文章1</title>
      <link>http://example.com/1</link>
      <description>文章1描述</description>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""
        feed = client._parse_rss(xml_content)
        assert feed.title == "测试订阅"
        assert len(feed.items) == 1
        assert feed.items[0].title == "文章1"


class TestRSSHubRoutes:
    """RSSHubRoutes 测试。"""

    def test_twitter_user(self) -> None:
        """测试 Twitter 用户路由。"""
        route = RSSHubRoutes.twitter_user("testuser")
        assert route == "/twitter/user/testuser"

    def test_telegram_channel(self) -> None:
        """测试 Telegram 频道路由。"""
        route = RSSHubRoutes.telegram_channel("testchannel")
        assert route == "/telegram/channel/testchannel"


class TestKafkaTopics:
    """KafkaTopics 测试。"""

    def test_topics_defined(self) -> None:
        """测试主题定义。"""
        assert KafkaTopics.INTEL_NEW == "intel.new"
        assert KafkaTopics.TASK_CREATED == "task.created"
        assert KafkaTopics.AUDIT_TOOL_CALL == "audit.tool_call"
