"""Playwright 抓取后端。

自研爬虫，支持：
- JavaScript 渲染
- 截图
- PDF 导出
- 内容提取
- 反检测
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, Field


class BrowserType(str, Enum):
    """浏览器类型。"""

    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class WaitStrategy(str, Enum):
    """等待策略。"""

    LOAD = "load"  # 页面加载完成
    DOMCONTENTLOADED = "domcontentloaded"  # DOM 内容加载完成
    NETWORKIDLE = "networkidle"  # 网络空闲
    COMMIT = "commit"  # 响应提交


class CrawlConfig(BaseModel):
    """抓取配置。"""

    # 浏览器配置
    browser_type: BrowserType = Field(
        default=BrowserType.CHROMIUM, description="浏览器类型"
    )
    headless: bool = Field(default=True, description="无头模式")
    viewport_width: int = Field(default=1920, description="视口宽度")
    viewport_height: int = Field(default=1080, description="视口高度")

    # 请求配置
    timeout_ms: int = Field(default=30000, description="超时时间（毫秒）")
    wait_strategy: WaitStrategy = Field(
        default=WaitStrategy.NETWORKIDLE, description="等待策略"
    )
    wait_after_load_ms: int = Field(default=1000, description="加载后额外等待（毫秒）")

    # 反检测配置
    stealth_mode: bool = Field(default=True, description="隐身模式")
    random_user_agent: bool = Field(default=True, description="随机 UA")
    block_resources: list[str] = Field(
        default_factory=lambda: ["image", "media", "font"],
        description="阻止加载的资源类型",
    )

    # 内容配置
    extract_text: bool = Field(default=True, description="提取文本")
    extract_html: bool = Field(default=True, description="提取 HTML")
    extract_links: bool = Field(default=True, description="提取链接")
    take_screenshot: bool = Field(default=False, description="截图")
    screenshot_full_page: bool = Field(default=False, description="全页截图")

    # 深度抓取
    max_depth: int = Field(default=1, description="最大抓取深度")
    max_pages: int = Field(default=10, description="最大页面数")
    same_domain_only: bool = Field(default=True, description="仅同域名")
    follow_links: bool = Field(default=False, description="跟踪链接")

    # 代理配置
    proxy: str | None = Field(default=None, description="代理服务器")


class Screenshot(BaseModel):
    """截图。"""

    data_base64: str = Field(description="Base64 编码的图片数据")
    format: str = Field(default="png", description="图片格式")
    width: int = Field(description="宽度")
    height: int = Field(description="高度")
    full_page: bool = Field(default=False, description="是否全页截图")


class PageContent(BaseModel):
    """页面内容。"""

    url: str = Field(description="页面 URL")
    final_url: str = Field(description="最终 URL（重定向后）")
    status_code: int = Field(description="HTTP 状态码")
    title: str = Field(description="页面标题")
    text: str | None = Field(default=None, description="提取的文本")
    html: str | None = Field(default=None, description="HTML 内容")
    links: list[str] = Field(default_factory=list, description="页面链接")
    screenshot: Screenshot | None = Field(default=None, description="截图")
    content_hash: str = Field(description="内容哈希")
    content_length: int = Field(description="内容长度")
    content_type: str | None = Field(default=None, description="内容类型")
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    load_time_ms: int = Field(description="加载时间（毫秒）")


class CrawlResult(BaseModel):
    """抓取结果。"""

    pages: list[PageContent] = Field(default_factory=list, description="抓取的页面")
    errors: list[str] = Field(default_factory=list, description="错误列表")
    stats: dict[str, int] = Field(default_factory=dict, description="统计信息")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    total_time_ms: int = 0


# 常见的 User-Agent 列表
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


@dataclass
class PlaywrightCrawler:
    """Playwright 抓取器。"""

    config: CrawlConfig = field(default_factory=CrawlConfig)

    # 内部状态
    _browser: Any = None
    _context: Any = None
    _visited_urls: set[str] = field(default_factory=set)
    _page_count: int = 0

    async def __aenter__(self) -> PlaywrightCrawler:
        """异步上下文管理器入口。"""
        await self._init_browser()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口。"""
        await self._close_browser()

    async def _init_browser(self) -> None:
        """初始化浏览器。"""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # 选择浏览器
        if self.config.browser_type == BrowserType.FIREFOX:
            browser_type = self._playwright.firefox
        elif self.config.browser_type == BrowserType.WEBKIT:
            browser_type = self._playwright.webkit
        else:
            browser_type = self._playwright.chromium

        # 启动浏览器
        launch_options: dict[str, Any] = {
            "headless": self.config.headless,
        }
        if self.config.proxy:
            launch_options["proxy"] = {"server": self.config.proxy}

        self._browser = await browser_type.launch(**launch_options)

        # 创建上下文
        context_options: dict[str, Any] = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
        }

        if self.config.random_user_agent:
            import random

            context_options["user_agent"] = random.choice(USER_AGENTS)

        self._context = await self._browser.new_context(**context_options)

        # 阻止资源
        if self.config.block_resources:
            await self._context.route(
                "**/*",
                lambda route: self._handle_route(route),
            )

    async def _handle_route(self, route: Any) -> None:
        """处理路由（阻止特定资源）。"""
        if route.request.resource_type in self.config.block_resources:
            await route.abort()
        else:
            await route.continue_()

    async def _close_browser(self) -> None:
        """关闭浏览器。"""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if hasattr(self, "_playwright"):
            await self._playwright.stop()

    async def crawl(self, url: str) -> CrawlResult:
        """抓取 URL。

        Args:
            url: 起始 URL

        Returns:
            抓取结果
        """
        result = CrawlResult()
        self._visited_urls.clear()
        self._page_count = 0

        await self._crawl_recursive(url, 0, result)

        result.completed_at = datetime.now(UTC)
        result.total_time_ms = int(
            (result.completed_at - result.started_at).total_seconds() * 1000
        )
        result.stats = {
            "pages_crawled": len(result.pages),
            "errors": len(result.errors),
            "total_time_ms": result.total_time_ms,
        }

        return result

    async def _crawl_recursive(
        self,
        url: str,
        depth: int,
        result: CrawlResult,
    ) -> None:
        """递归抓取。"""
        # 检查限制
        if depth > self.config.max_depth:
            return
        if self._page_count >= self.config.max_pages:
            return
        if url in self._visited_urls:
            return

        self._visited_urls.add(url)
        self._page_count += 1

        try:
            page_content = await self._fetch_page(url)
            result.pages.append(page_content)

            # 跟踪链接
            if (
                self.config.follow_links
                and depth < self.config.max_depth
                and self._page_count < self.config.max_pages
            ):
                for link in page_content.links:
                    if self._should_follow_link(url, link):
                        await self._crawl_recursive(link, depth + 1, result)

        except Exception as e:
            result.errors.append(f"{url}: {str(e)}")

    async def _fetch_page(self, url: str) -> PageContent:
        """抓取单个页面。"""
        import time

        start_time = time.monotonic()

        page = await self._context.new_page()
        try:
            # 导航到页面
            response = await page.goto(
                url,
                wait_until=self.config.wait_strategy.value,
                timeout=self.config.timeout_ms,
            )

            # 额外等待
            if self.config.wait_after_load_ms > 0:
                await asyncio.sleep(self.config.wait_after_load_ms / 1000)

            # 获取最终 URL
            final_url = page.url

            # 获取标题
            title = await page.title()

            # 提取文本
            text = None
            if self.config.extract_text:
                text = await page.inner_text("body")

            # 提取 HTML
            html = None
            if self.config.extract_html:
                html = await page.content()

            # 提取链接
            links: list[str] = []
            if self.config.extract_links:
                link_elements = await page.query_selector_all("a[href]")
                for elem in link_elements:
                    href = await elem.get_attribute("href")
                    if href:
                        absolute_url = urljoin(final_url, href)
                        links.append(absolute_url)

            # 截图
            screenshot = None
            if self.config.take_screenshot:
                screenshot_bytes = await page.screenshot(
                    full_page=self.config.screenshot_full_page,
                    type="png",
                )
                screenshot = Screenshot(
                    data_base64=base64.b64encode(screenshot_bytes).decode("ascii"),
                    format="png",
                    width=self.config.viewport_width,
                    height=self.config.viewport_height,
                    full_page=self.config.screenshot_full_page,
                )

            # 计算内容哈希
            content_for_hash = (text or html or "").encode("utf-8")
            content_hash = hashlib.sha256(content_for_hash).hexdigest()

            load_time_ms = int((time.monotonic() - start_time) * 1000)

            return PageContent(
                url=url,
                final_url=final_url,
                status_code=response.status if response else 0,
                title=title,
                text=text,
                html=html,
                links=links[:100],  # 限制链接数量
                screenshot=screenshot,
                content_hash=content_hash,
                content_length=len(content_for_hash),
                content_type=response.headers.get("content-type") if response else None,
                load_time_ms=load_time_ms,
            )

        finally:
            await page.close()

    def _should_follow_link(self, base_url: str, link: str) -> bool:
        """判断是否应该跟踪链接。"""
        # 跳过非 HTTP 链接
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https", ""}:
            return False

        # 跳过锚点和 JavaScript
        if link.startswith("#") or link.startswith("javascript:"):
            return False

        # 同域名限制
        if self.config.same_domain_only:
            base_domain = urlparse(base_url).netloc
            link_domain = parsed.netloc
            if link_domain and link_domain != base_domain:
                return False

        return True

    async def fetch_single(self, url: str) -> PageContent:
        """抓取单个页面（不递归）。

        Args:
            url: 页面 URL

        Returns:
            页面内容
        """
        return await self._fetch_page(url)


async def crawl_url(
    url: str,
    config: CrawlConfig | None = None,
) -> CrawlResult:
    """便捷函数：抓取 URL。

    Args:
        url: 起始 URL
        config: 抓取配置

    Returns:
        抓取结果
    """
    crawler = PlaywrightCrawler(config=config or CrawlConfig())
    async with crawler:
        return await crawler.crawl(url)


async def fetch_page(
    url: str,
    config: CrawlConfig | None = None,
) -> PageContent:
    """便捷函数：抓取单个页面。

    Args:
        url: 页面 URL
        config: 抓取配置

    Returns:
        页面内容
    """
    crawler = PlaywrightCrawler(config=config or CrawlConfig())
    async with crawler:
        return await crawler.fetch_single(url)
