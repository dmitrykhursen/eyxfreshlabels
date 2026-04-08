"""
Async Playwright base scraper.

All competitor scrapers inherit from BaseScraper and override:
  - COMPETITOR_KEY  (str)
  - discover_brands(freshlabels_brands) -> dict[brand_name, url]
  - scrape_brand_page(page, brand_name, url) -> list[dict]
"""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

MAX_RETRIES = 3
BASE_DELAY = 2.0       # seconds between requests
JITTER = 1.5           # ± random added to delay


class BaseScraper(ABC):
    """
    Async Playwright base scraper with retry, delay, and UA rotation.

    Usage:
        scraper = QueensScraper()
        await scraper.launch()
        try:
            brand_map = await scraper.discover_brands(freshlabels_brands)
            products  = await scraper.scrape_all_brands(brand_map)
        finally:
            await scraper.close()
    """

    COMPETITOR_KEY: str = ""  # override in subclass, e.g. "queens"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None

    async def launch(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        logger.info("[%s] Browser launched", self.COMPETITOR_KEY)

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("[%s] Browser closed", self.COMPETITOR_KEY)

    async def new_context(self) -> BrowserContext:
        return await self._browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 900},
            locale="cs-CZ",
            extra_http_headers={"Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8"},
        )

    async def get_page(self, url: str) -> tuple[Page, str]:
        """
        Navigate to URL, return (page, html). Retries up to MAX_RETRIES times.
        Caller is responsible for closing the context/page.
        """
        context = await self.new_context()
        page = await context.new_page()

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await asyncio.sleep(BASE_DELAY + random.uniform(-JITTER, JITTER))
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(random.randint(1500, 3000))
                html = await page.content()
                return page, html
            except Exception as exc:
                wait = 2 ** attempt
                logger.warning(
                    "[%s] Attempt %d/%d failed for %s: %s — retrying in %ds",
                    self.COMPETITOR_KEY, attempt, MAX_RETRIES, url, exc, wait,
                )
                if attempt == MAX_RETRIES:
                    await context.close()
                    raise
                await asyncio.sleep(wait)

    def parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    async def scroll_to_bottom(self, page: Page, pause_ms: int = 1200) -> None:
        """
        Scroll incrementally to trigger lazy-loaded content.
        Stops when scroll height stabilises for 2 consecutive checks.
        """
        prev_height = -1
        stable_count = 0
        while stable_count < 2:
            curr_height = await page.evaluate("document.body.scrollHeight")
            if curr_height == prev_height:
                stable_count += 1
            else:
                stable_count = 0
            prev_height = curr_height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(pause_ms)

    # ------------------------------------------------------------------
    # Abstract interface — implement in each competitor scraper
    # ------------------------------------------------------------------

    @abstractmethod
    async def discover_brands(self, freshlabels_brands: list[str]) -> dict[str, str]:
        """
        Return dict: {freshlabels_brand_name: competitor_brand_url}
        For brands not found on the competitor, omit them (caller records as absent).
        """

    @abstractmethod
    async def scrape_brand_page(self, page: Page, brand_name: str, url: str) -> list[dict]:
        """
        Parse an already-loaded brand page and return list of product dicts.
        Each dict must contain: product_name, brand, price_czk,
        discounted_price_czk, is_discounted, discount_pct, url, competitor, scraped_at.
        """

    # ------------------------------------------------------------------
    # Orchestration — shared by all scrapers
    # ------------------------------------------------------------------

    async def scrape_all_brands(
        self,
        brand_url_map: dict[str, str],
        freshlabels_brands: list[str],
    ) -> tuple[list[dict], dict[str, bool]]:
        """
        Scrape all brands. Returns:
          - products: flat list of all scraped product dicts
          - presence: {brand_name: True/False} indicating competitor carries it
        """
        products = []
        presence = {b: False for b in freshlabels_brands}

        for brand_name, url in brand_url_map.items():
            logger.info("[%s] Scraping brand: %s", self.COMPETITOR_KEY, brand_name)
            try:
                context = await self.new_context()
                page = await context.new_page()
                await asyncio.sleep(BASE_DELAY + random.uniform(-JITTER, JITTER))
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(random.randint(2000, 3500))
                await self.scroll_to_bottom(page)

                brand_products = await self.scrape_brand_page(page, brand_name, url)
                await context.close()
                

                if brand_products:
                    presence[brand_name] = True
                    products.extend(brand_products)
                    logger.info(
                        "[%s] %s: %d products", self.COMPETITOR_KEY, brand_name, len(brand_products)
                    )
                else:
                    logger.info("[%s] %s: 0 products (not carried)", self.COMPETITOR_KEY, brand_name)

            except Exception as exc:
                logger.error("[%s] Failed to scrape %s: %s", self.COMPETITOR_KEY, brand_name, exc)
                try:
                    await context.close()
                except Exception:
                    pass

        return products, presence
