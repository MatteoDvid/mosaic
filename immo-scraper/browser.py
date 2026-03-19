from __future__ import annotations
import os
import random
from typing import AsyncGenerator
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import stealth_async

from config import USER_AGENTS, NAV_DELAY_MIN, NAV_DELAY_MAX
from utils import random_delay


def _detect_proxy() -> dict | None:
    """Detect HTTP proxy from environment and return Playwright proxy config."""
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or \
                os.environ.get("https_proxy") or os.environ.get("http_proxy")
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    if not parsed.hostname:
        return None
    config: dict = {"server": f"http://{parsed.hostname}:{parsed.port}"}
    if parsed.username:
        config["username"] = parsed.username
    if parsed.password:
        config["password"] = parsed.password
    return config


class BrowserSession:
    """
    Async context manager that owns a single Playwright browser + context.
    Usage:
        async with BrowserSession() as session:
            page = await session.new_page()
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._user_agent = random.choice(USER_AGENTS)

    async def __aenter__(self) -> "BrowserSession":
        self._playwright_ctx = async_playwright()
        self._playwright = await self._playwright_ctx.__aenter__()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        proxy_config = _detect_proxy()
        self._context = await self._browser.new_context(
            user_agent=self._user_agent,
            viewport={"width": 1366, "height": 768},
            locale="fr-FR",
            timezone_id="Europe/Paris",
            ignore_https_errors=True if proxy_config else False,
            **({"proxy": proxy_config} if proxy_config else {}),
        )
        return self

    async def new_page(self) -> Page:
        assert self._context is not None, "BrowserSession not started"
        page = await self._context.new_page()
        await stealth_async(page)
        return page

    async def navigate(self, page: Page, url: str, wait_until: str = "domcontentloaded") -> None:
        """Navigate with random delay to mimic human browsing."""
        await random_delay(NAV_DELAY_MIN, NAV_DELAY_MAX)
        await page.goto(url, wait_until=wait_until, timeout=30_000)

    async def __aexit__(self, *args) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright_ctx:
            await self._playwright_ctx.__aexit__(*args)
