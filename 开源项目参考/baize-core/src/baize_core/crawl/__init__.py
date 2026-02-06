"""抓取模块。

包含 Playwright 抓取后端。
"""

from baize_core.crawl.playwright_backend import (
    CrawlConfig,
    CrawlResult,
    PageContent,
    PlaywrightCrawler,
    Screenshot,
)

__all__ = [
    "CrawlConfig",
    "CrawlResult",
    "PageContent",
    "PlaywrightCrawler",
    "Screenshot",
]
