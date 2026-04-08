"""
nila.cz competitor scraper.

nila.cz is a Czech sustainable/ethical fashion e-shop (PrestaShop CMS, SSR).
Products ARE present in the initial HTML — Playwright is still used to handle
lazy-loading and cookie/consent banners that might block content.

Brand discovery: scrape https://www.nila.cz/znacky/ to find all brand slugs,
fuzzy-match against Freshlabels brands.

Brand page URLs:  https://www.nila.cz/znacky/{brand-slug}/
Products per page are limited; pagination handled via ?page=N.
"""

import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import Page
from rapidfuzz import fuzz, process

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL   = "https://www.nila.cz"
BRANDS_URL = f"{BASE_URL}/znacky/"
RAW_DIR    = "data/competitors/nila"

# Max pages to try per brand (safety cap)
MAX_PAGES = 20


def _slugify(name: str) -> str:
    """Convert brand name to URL slug."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def _parse_price(text: str) -> Optional[float]:
    """
    Extract numeric price from strings like '3 999 Kč', '4\xa0599\xa0Kč'.
    Returns float or None.
    """
    # Remove currency symbol and whitespace variants
    cleaned = re.sub(r"[^\d]", "", text)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


class NilaScraper(BaseScraper):
    COMPETITOR_KEY = "nila"

    # ------------------------------------------------------------------
    # Brand discovery
    # ------------------------------------------------------------------

    async def discover_brands(self, freshlabels_brands: list[str]) -> dict[str, str]:
        """
        Scrapes /znacky/ for brand slugs, fuzzy-matches FL brands.
        Returns {freshlabels_brand_name: nila_brand_url}.
        """
        logger.info("[nila] Discovering brands at %s", BRANDS_URL)
        page, html = await self.get_page(BRANDS_URL)

        # Dismiss cookie banner if present and wait for brand links
        try:
            accept_btn = page.locator("#cookiescript_accept")
            if await accept_btn.count() > 0:
                await accept_btn.click()
                await page.wait_for_timeout(800)
        except Exception:
            pass

        # Wait for brand links to appear
        try:
            await page.wait_for_selector("a[href*='/znacky/']", timeout=12_000)
            html = await page.content()
        except Exception:
            logger.warning("[nila] Timeout waiting for brand links — using raw HTML")
        await page.context.close()

        soup = BeautifulSoup(html, "lxml")

        # Extract /znacky/{slug}/ links — filter out the listing page itself
        nila_brands: dict[str, str] = {}  # slug → full url
        pattern = re.compile(r"^/znacky/([^/]+)/?$")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http"):
                # Only care about nila.cz hrefs
                if "nila.cz" not in href:
                    continue
                href_path = href.replace(BASE_URL, "")
            else:
                href_path = href

            m = pattern.match(href_path)
            if m:
                slug = m.group(1)
                if slug and slug != "znacky":
                    full_url = f"{BASE_URL}/znacky/{slug}/"
                    nila_brands[slug] = full_url

        logger.info("[nila] Found %d brands on nila.cz", len(nila_brands))

        # Save raw brand map
        os.makedirs(RAW_DIR, exist_ok=True)
        map_path = f"{RAW_DIR}/brand_slug_map.json"
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(nila_brands, f, ensure_ascii=False, indent=2)
        logger.info("[nila] Brand slug map saved → %s", map_path)

        if not nila_brands:
            logger.warning("[nila] No brands found — check selector or page structure")
            return {}

        # Fuzzy-match Freshlabels brands → nila slugs
        matched: dict[str, str] = {}
        nila_slugs = list(nila_brands.keys())

        for fl_brand in freshlabels_brands:
            fl_slug = _slugify(fl_brand)

            # 1. Exact slug match
            if fl_slug in nila_brands:
                matched[fl_brand] = nila_brands[fl_slug]
                continue

            # 2. Fuzzy match (score ≥ 80)
            result = process.extractOne(
                fl_slug, nila_slugs, scorer=fuzz.token_sort_ratio
            )
            if result and result[1] >= 80:
                best_slug = result[0]
                matched[fl_brand] = nila_brands[best_slug]
                logger.debug(
                    "[nila] Fuzzy match: '%s' → '%s' (score %d)",
                    fl_brand, best_slug, result[1],
                )

        logger.info(
            "[nila] Matched %d / %d Freshlabels brands",
            len(matched), len(freshlabels_brands),
        )
        return matched

    # ------------------------------------------------------------------
    # Product scraping — handles pagination
    # ------------------------------------------------------------------

    async def scrape_brand_page(self, page: Page, brand_name: str, url: str) -> list[dict]:
        """
        Collect products across all pages for a brand.
        nila.cz uses ?page=N pagination.
        """
        all_products: list[dict] = []

        # Page 1 is already loaded in the browser (from scrape_all_brands)
        for page_num in range(1, MAX_PAGES + 1):
            if page_num > 1:
                paged_url = f"{url}?page={page_num}"
                try:
                    await page.goto(paged_url, wait_until="domcontentloaded", timeout=30_000)
                    await page.wait_for_timeout(1200)
                except Exception as exc:
                    logger.warning("[nila] Could not load page %d for %s: %s", page_num, brand_name, exc)
                    break

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")
            scraped_at = datetime.now(timezone.utc).isoformat()

            # Find product cards — nila uses <a class="js-product-item item">
            cards = soup.select("a.js-product-item") or soup.select("a[class*='js-product-item']")

            if not cards:
                # No products on this page → pagination exhausted
                if page_num == 1:
                    logger.debug("[nila] No product cards on first page for %s", brand_name)
                break

            page_products = []
            for card in cards:
                try:
                    product = self._parse_card(card, brand_name, scraped_at)
                    if product:
                        page_products.append(product)
                except Exception as exc:
                    logger.debug("[nila] Card parse error for %s: %s", brand_name, exc)

            all_products.extend(page_products)
            logger.debug("[nila] %s page %d: %d products", brand_name, page_num, len(page_products))

            # Check if there's a "next page" link — if not, stop
            next_page = soup.select_one(
                "a.next, a[class*='next'], a[rel='next'], "
                "li.next > a, .pagination a[href*='page=']"
            )
            if not next_page:
                break

        return all_products

    def _parse_card(self, card, brand_name: str, scraped_at: str) -> Optional[dict]:
        """
        Parse a single product card <a> element from nila.cz.

        Structure:
            <a class="js-product-item item" href="/.../">
              <div class="img-part">...</div>
              <div class="item-bottom">
                <div class="item-descr">
                  <h4>Product Name</h4>
                  <small class="znacka">Brand</small>
                  <div class="price">
                    [<del>3 999 Kč</del>]   ← original if on sale
                    <span>2 999 Kč</span>    ← current price
                  </div>
                </div>
              </div>
            </a>
        """
        # 1. Product name
        name_el = card.select_one("h4")
        if not name_el:
            return None
        product_name = name_el.get_text(strip=True)
        if not product_name:
            return None

        # 2. URL
        href = card.get("href", "")
        product_url = href if href.startswith("http") else BASE_URL + href

        # 3. Brand (from card if available, else passed-in brand_name)
        brand_el = card.select_one("small.znacka, [class*='znacka']")
        scraped_brand = brand_el.get_text(strip=True) if brand_el else brand_name

        # 4. Price — original (crossed-out) and current
        price_block = card.select_one(".price")
        if not price_block:
            return None

        # Original price: in <del> tag if discounted
        del_el = price_block.select_one("del")
        # Current price: plain <span> (NOT inside <del>)
        span_els = price_block.find_all("span", recursive=False)
        if not span_els:
            # Try any span
            span_els = price_block.select("span")

        current_price_text = span_els[0].get_text(strip=True) if span_els else ""
        current_price = _parse_price(current_price_text)

        if current_price is None:
            return None

        if del_el:
            original_price = _parse_price(del_el.get_text(strip=True))
        else:
            original_price = None

        # Determine price_czk (original) vs discounted_price_czk
        if original_price and original_price > current_price:
            price_czk = original_price
            discounted_price_czk = current_price
            is_discounted = True
            discount_pct = round((price_czk - discounted_price_czk) / price_czk * 100, 1)
        else:
            price_czk = current_price
            discounted_price_czk = None
            is_discounted = False
            discount_pct = None

        return {
            "product_name": product_name,
            "brand": brand_name,           # use FL-matched brand name for joining
            "scraped_brand": scraped_brand, # actual text from the page
            "price_czk": price_czk,
            "discounted_price_czk": discounted_price_czk,
            "is_discounted": is_discounted,
            "discount_pct": discount_pct,
            "url": product_url,
            "competitor": self.COMPETITOR_KEY,
            "scraped_at": scraped_at,
        }
