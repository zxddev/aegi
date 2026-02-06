"""Huginn 规则采集适配器。

提供规则化自动采集能力：
- Scenario 创建与管理
- 采集结果接收 (Webhook)
- 转换为 Artifact/Chunk
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class HuginnConfig:
    """Huginn 配置。"""

    base_url: str = "http://localhost:3000"
    api_token: str = ""
    timeout: int = 30


@dataclass
class Agent:
    """Huginn Agent 定义。"""

    name: str
    agent_type: str  # WebsiteAgent, RssAgent, etc.
    options: dict[str, Any]
    schedule: str = "every_1h"
    keep_events_for: int = 604800  # 7 days in seconds
    propagate_immediately: bool = True
    sources: list[int] = field(default_factory=list)


@dataclass
class Scenario:
    """Huginn Scenario（工作流）。"""

    name: str
    description: str = ""
    agents: list[Agent] = field(default_factory=list)
    public: bool = False


@dataclass
class Event:
    """Huginn Event（采集结果）。"""

    event_id: int
    agent_id: int
    agent_name: str
    payload: dict[str, Any]
    created_at: datetime


class HuginnClient:
    """Huginn API 客户端。"""

    def __init__(self, config: HuginnConfig) -> None:
        """初始化客户端。

        Args:
            config: 配置
        """
        self._config = config
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        """建立连接。"""
        headers = {
            "Content-Type": "application/json",
        }
        if self._config.api_token:
            headers["Authorization"] = f"Token {self._config.api_token}"

        timeout = aiohttp.ClientTimeout(total=self._config.timeout)
        self._session = aiohttp.ClientSession(
            headers=headers,
            timeout=timeout,
        )
        logger.info("Huginn 客户端已连接: %s", self._config.base_url)

    async def close(self) -> None:
        """关闭连接。"""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Huginn 客户端已关闭")

    async def __aenter__(self) -> HuginnClient:
        """异步上下文管理器入口。"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口。"""
        await self.close()

    # ============ Scenario 管理 ============

    async def create_scenario(self, scenario: Scenario) -> int:
        """创建 Scenario。

        Args:
            scenario: Scenario 定义

        Returns:
            Scenario ID
        """
        payload = {
            "scenario": {
                "name": scenario.name,
                "description": scenario.description,
                "public": scenario.public,
            }
        }
        result = await self._post("/scenarios.json", payload)
        scenario_id = result.get("id", 0)
        logger.info("创建 Scenario: %s -> %d", scenario.name, scenario_id)

        # 创建 Agents
        for agent in scenario.agents:
            await self.create_agent(agent, scenario_id)

        return scenario_id

    async def get_scenario(self, scenario_id: int) -> dict[str, Any]:
        """获取 Scenario 详情。"""
        return await self._get(f"/scenarios/{scenario_id}.json")

    async def list_scenarios(self) -> list[dict[str, Any]]:
        """列出所有 Scenarios。"""
        result = await self._get("/scenarios.json")
        return result if isinstance(result, list) else []

    async def delete_scenario(self, scenario_id: int) -> None:
        """删除 Scenario。"""
        await self._delete(f"/scenarios/{scenario_id}.json")
        logger.info("删除 Scenario: %d", scenario_id)

    # ============ Agent 管理 ============

    async def create_agent(
        self,
        agent: Agent,
        scenario_id: int | None = None,
    ) -> int:
        """创建 Agent。

        Args:
            agent: Agent 定义
            scenario_id: 所属 Scenario ID

        Returns:
            Agent ID
        """
        payload = {
            "agent": {
                "name": agent.name,
                "type": f"Agents::{agent.agent_type}",
                "options": agent.options,
                "schedule": agent.schedule,
                "keep_events_for": agent.keep_events_for,
                "propagate_immediately": agent.propagate_immediately,
            }
        }

        if scenario_id:
            payload["agent"]["scenario_ids"] = [scenario_id]
        if agent.sources:
            payload["agent"]["source_ids"] = agent.sources

        result = await self._post("/agents.json", payload)
        agent_id = result.get("id", 0)
        logger.info("创建 Agent: %s -> %d", agent.name, agent_id)
        return agent_id

    async def get_agent(self, agent_id: int) -> dict[str, Any]:
        """获取 Agent 详情。"""
        return await self._get(f"/agents/{agent_id}.json")

    async def list_agents(self) -> list[dict[str, Any]]:
        """列出所有 Agents。"""
        result = await self._get("/agents.json")
        return result if isinstance(result, list) else []

    async def run_agent(self, agent_id: int) -> None:
        """立即运行 Agent。"""
        await self._post(f"/agents/{agent_id}/run.json", {})
        logger.info("运行 Agent: %d", agent_id)

    async def delete_agent(self, agent_id: int) -> None:
        """删除 Agent。"""
        await self._delete(f"/agents/{agent_id}.json")
        logger.info("删除 Agent: %d", agent_id)

    # ============ Event 管理 ============

    async def get_events(
        self,
        agent_id: int | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """获取 Events。

        Args:
            agent_id: Agent ID（可选，不指定则获取所有）
            limit: 最大数量

        Returns:
            Event 列表
        """
        if agent_id:
            result = await self._get(f"/agents/{agent_id}/events.json?per_page={limit}")
        else:
            result = await self._get(f"/events.json?per_page={limit}")

        events = []
        for item in result if isinstance(result, list) else []:
            events.append(
                Event(
                    event_id=item.get("id", 0),
                    agent_id=item.get("agent_id", 0),
                    agent_name=item.get("agent", {}).get("name", ""),
                    payload=item.get("payload", {}),
                    created_at=datetime.fromisoformat(
                        item.get("created_at", datetime.now(UTC).isoformat()).replace(
                            "Z", "+00:00"
                        )
                    ),
                )
            )
        return events

    async def delete_events(self, agent_id: int) -> None:
        """删除 Agent 的所有 Events。"""
        await self._delete(f"/agents/{agent_id}/events.json")
        logger.info("删除 Events: agent_id=%d", agent_id)

    # ============ Artifact/Chunk 转换 ============

    def events_to_artifacts(
        self,
        events: list[Event],
    ) -> list[dict[str, Any]]:
        """将 Events 转换为 Artifact 格式。

        Args:
            events: Event 列表

        Returns:
            Artifact 格式的字典列表
        """
        artifacts = []
        for event in events:
            # 提取 URL（如果有）
            payload = event.payload
            url = payload.get("url") or payload.get("link") or ""

            # 提取内容
            content = (
                payload.get("content")
                or payload.get("body")
                or payload.get("description")
                or ""
            )

            if not content:
                continue

            artifacts.append(
                {
                    "artifact_uid": str(uuid4()),
                    "origin_url": url,
                    "origin_tool": f"huginn/{event.agent_name}",
                    "fetched_at": event.created_at.isoformat(),
                    "content": content,
                    "metadata": {
                        "huginn_event_id": event.event_id,
                        "huginn_agent_id": event.agent_id,
                        "title": payload.get("title", ""),
                    },
                }
            )
        return artifacts

    # ============ 预定义 Scenario 模板 ============

    def create_rss_scenario_template(
        self,
        name: str,
        feed_urls: list[str],
    ) -> Scenario:
        """创建 RSS 采集 Scenario 模板。

        Args:
            name: Scenario 名称
            feed_urls: RSS 源 URL 列表

        Returns:
            Scenario 定义
        """
        agents = []
        for i, url in enumerate(feed_urls):
            agents.append(
                Agent(
                    name=f"RSS_{i + 1}",
                    agent_type="RssAgent",
                    options={
                        "url": url,
                        "expected_update_period_in_days": 1,
                    },
                    schedule="every_1h",
                )
            )

        return Scenario(
            name=name,
            description=f"RSS 采集: {len(feed_urls)} 个源",
            agents=agents,
        )

    def create_website_scenario_template(
        self,
        name: str,
        url: str,
        css_selector: str,
    ) -> Scenario:
        """创建网页采集 Scenario 模板。

        Args:
            name: Scenario 名称
            url: 目标 URL
            css_selector: CSS 选择器

        Returns:
            Scenario 定义
        """
        return Scenario(
            name=name,
            description=f"网页采集: {url}",
            agents=[
                Agent(
                    name="WebsiteScraper",
                    agent_type="WebsiteAgent",
                    options={
                        "url": url,
                        "type": "html",
                        "mode": "on_change",
                        "extract": {
                            "content": {"css": css_selector, "value": "."},
                        },
                    },
                    schedule="every_1h",
                ),
            ],
        )

    # ============ 内部方法 ============

    async def _get(self, path: str) -> Any:
        """发送 GET 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._config.base_url}{path}"
        async with self._session.get(url) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"Huginn API 错误: {resp.status} - {text}")
            return await resp.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送 POST 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._config.base_url}{path}"
        async with self._session.post(url, json=payload) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"Huginn API 错误: {resp.status} - {text}")
            return await resp.json()

    async def _delete(self, path: str) -> None:
        """发送 DELETE 请求。"""
        if not self._session:
            raise RuntimeError("客户端未连接")

        url = f"{self._config.base_url}{path}"
        async with self._session.delete(url) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"Huginn API 错误: {resp.status} - {text}")


def get_huginn_config_from_env() -> HuginnConfig:
    """从环境变量获取配置。"""
    import os

    return HuginnConfig(
        base_url=os.getenv("HUGINN_URL", "http://localhost:3000"),
        api_token=os.getenv("HUGINN_API_TOKEN", ""),
        timeout=int(os.getenv("HUGINN_TIMEOUT", "30")),
    )
