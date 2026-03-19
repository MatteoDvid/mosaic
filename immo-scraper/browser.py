from __future__ import annotations
import random
from typing import AsyncGenerator

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import stealth_async

from config import USER_AGENTS, NAV_DELAY_MIN, NAV_DELAY_MAX
from utils import random_delay


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
        self._context = await self._browser.new_context(
            user_agent=self._user_agent,
            viewport={"width": 1366, "height": 768},
            locale="fr-FR",
            timezone_id="Europe/Paris",
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
