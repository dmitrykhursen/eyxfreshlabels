"""
Queens.cz competitor scraper.

queens.cz uses the same PrestaShop + React frontend as Footshop (shared ownership).
Brand URLs follow: https://www.queens.cz/cs/{numeric_id}_{brand-slug}
The page is JS-rendered — products are NOT in the initial HTML.

Brand discovery: scrape /cs/znacky to get id→slug mapping, then fuzzy-match
against Freshlabels brand names.
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

BASE_URL = "https://www.queens.cz"
BRANDS_URL = f"{BASE_URL}/cs/znacky"
RAW_DIR = "data/competitors/queens"


def _slugify(name: str) -> str:
    """Convert brand name to URL slug (approximate)."""
    # Normalise unicode: Fjällräven → fjallraven
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def _parse_price(text: str) -> Optional[float]:
    """Extract numeric price from strings like '4 990 Kč' or '4990 Kč'."""
    cleaned = re.sub(r"[^\d,.]", "", text.replace("\xa0", "").replace(" ", ""))
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


class QueensScraper(BaseScraper):
    COMPETITOR_KEY = "queens"

    # ------------------------------------------------------------------
    # Brand discovery
    # ------------------------------------------------------------------

    async def discover_brands(self, freshlabels_brands: list[str]) -> dict[str, str]:
        """
        Scrapes /cs/znacky, builds slug→(id, slug) map from anchor hrefs,
        then fuzzy-matches each Freshlabels brand against queens slugs.
        Returns {freshlabels_brand_name: full_queens_brand_url}.
        """
        logger.info("[queens] Discovering brands at %s", BRANDS_URL)
        page, html = await self.get_page(BRANDS_URL)

        # Wait for brand links to render
        try:
            await page.wait_for_selector("a[href*='_']", timeout=15_000)
            html = await page.content()
        except Exception:
            logger.warning("[queens] Timeout waiting for brand links — using raw HTML")
        await page.context.close()

        soup = BeautifulSoup(html, "lxml")

        # Extract all /cs/{id}_{slug} links from the brands page
        queens_brands: dict[str, str] = {}  # slug → full url
        pattern = re.compile(r"/cs/(\d+)_([a-z0-9-]+)$")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Make absolute
            if href.startswith("/"):
                href = BASE_URL + href
            m = pattern.search(href)
            if m:
                brand_id, brand_slug = m.group(1), m.group(2)
                queens_brands[brand_slug] = href

        logger.info("[queens] Found %d brands on queens.cz", len(queens_brands))

        # Save raw brand map
        os.makedirs(RAW_DIR, exist_ok=True)
        id_map_path = f"{RAW_DIR}/brand_id_map.json"
        with open(id_map_path, "w", encoding="utf-8") as f:
            json.dump(queens_brands, f, ensure_ascii=False, indent=2)
        logger.info("[queens] Brand ID map saved → %s", id_map_path)

        # Fuzzy-match Freshlabels brands → queens slugs
        matched: dict[str, str] = {}
        queens_slugs = list(queens_brands.keys())

        for fl_brand in freshlabels_brands:
            fl_slug = _slugify(fl_brand)

            # 1. Exact slug match
            if fl_slug in queens_brands:
                matched[fl_brand] = queens_brands[fl_slug]
                continue

            # 2. Fuzzy match against queen slugs (score ≥ 85)
            result = process.extractOne(
                fl_slug, queens_slugs, scorer=fuzz.token_sort_ratio
            )
            if result and result[1] >= 85:
                best_slug = result[0]
                matched[fl_brand] = queens_brands[best_slug]
                logger.debug("[queens] Fuzzy match: '%s' → '%s' (score %d)", fl_brand, best_slug, result[1])

        logger.info(
            "[queens] Matched %d / %d Freshlabels brands",
            len(matched), len(freshlabels_brands),
        )
        return matched

    # ------------------------------------------------------------------
    # Product scraping
    # ------------------------------------------------------------------

    async def scrape_brand_page(self, page: Page, brand_name: str, url: str) -> list[dict]:
        """
        Parse a fully-loaded queens.cz brand page.
        """
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        scraped_at = datetime.now(timezone.utc).isoformat()

        products = []

        # Queens.cz now uses Schema.org metadata and 'Product_wrapper' for grid items
        cards = (
            soup.select("[itemprop='itemListElement']")
            or soup.select("div[class*='Product_wrapper']")
            or soup.select("[class*='ProductList_item']")
        )

        print(f"[queens] Found {len(cards)} product cards for {brand_name}")

        if not cards:
            logger.debug("[queens] No product cards found for %s via CSS — trying link fallback", brand_name)
            cards = soup.select("a[href*='/cs/p/'], a[href*='/product/']")

        for card in cards:
            try:
                product = self._parse_card(card, brand_name, url, scraped_at)
                if product:
                    products.append(product)
            except Exception as exc:
                logger.debug("[queens] Card parse error: %s", exc)

        return products

    def _parse_card(self, card, brand_name: str, page_url: str, scraped_at: str) -> Optional[dict]:
        """Extract fields from a single product card element utilizing Schema.org where available."""
        # 1. Product name
        name_meta = card.select_one("meta[itemprop='name']")
        if name_meta and name_meta.get("content"):
            product_name = name_meta["content"]
        else:
            name_el = card.select_one("[class*='Product_name'], [class*='product-name'], h2, h3, h4")
            product_name = name_el.get_text(strip=True) if name_el else ""
            
        if not product_name:
            return None

        # 2. Product URL
        url_meta = card.select_one("meta[itemprop='url']")
        if url_meta and url_meta.get("content"):
            product_url = url_meta["content"]
            if not product_url.startswith("http"):
                product_url = BASE_URL + product_url
        else:
            link_el = card.find("a", href=True) if card.name != "a" else card
            product_url = ""
            if link_el and link_el.get("href"):
                href = link_el["href"]
                product_url = href if href.startswith("http") else BASE_URL + href

        price_czk = None
        discounted_price_czk = None

        # 3. Prices
        # Attempt to grab current price securely via schema metadata
        price_meta = card.select_one("meta[itemprop='price']")
        current_price = None
        if price_meta and price_meta.get("content"):
            try:
                current_price = float(price_meta["content"])
            except ValueError:
                pass

        # Grab old price explicitly from the .oldPrice or <del> spans to compute discount
        old_price_el = card.select_one("[class*='oldPrice'], [class*='old-price'], [class*='OldPrice'], del")
        if old_price_el:
            price_czk = _parse_price(old_price_el.get_text(strip=True))

        if not current_price:
            # Fallback: Current price is normally wrapped in a <strong> tag if HTML changed
            current_price_el = card.select_one("strong")
            if current_price_el:
                current_price = _parse_price(current_price_el.get_text(strip=True))

        if current_price:
            if price_czk is None or price_czk <= current_price:
                price_czk = current_price  # Product is not discounted
                discounted_price_czk = None
            else:
                discounted_price_czk = current_price
        else:
            # Failed to find any price at all
            return None

        # Verify discount values
        is_discounted = discounted_price_czk is not None and discounted_price_czk < price_czk
        discount_pct = None
        if is_discounted and price_czk > 0:
            discount_pct = round((price_czk - discounted_price_czk) / price_czk * 100, 1)

        return {
            "product_name": product_name,
            "brand": brand_name,
            "price_czk": price_czk,
            "discounted_price_czk": discounted_price_czk,
            "is_discounted": is_discounted,
            "discount_pct": discount_pct,
            "url": product_url,
            "competitor": self.COMPETITOR_KEY,
            "scraped_at": scraped_at,
        }