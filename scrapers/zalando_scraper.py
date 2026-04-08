"""
Zalando.cz competitor scraper.

Zalando heavily splits their catalog by gender. Brand pages are accessed 
via category filters (e.g., /damske-obleceni/{brand-slug}/).
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

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.zalando.cz"
RAW_DIR = "data/competitors/zalando"

def _slugify(name: str) -> str:
    """Convert brand name to URL slug for Zalando."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")

def _parse_price(text: str) -> Optional[float]:
    """Extract numeric price from strings like '1 500,00 Kč'."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d,.]", "", text.replace("\xa0", "").replace(" ", ""))
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None

class ZalandoScraper(BaseScraper):
    COMPETITOR_KEY = "zalando"

    # ------------------------------------------------------------------
    # Brand discovery
    # ------------------------------------------------------------------

    async def discover_brands(self, freshlabels_brands: list[str]) -> dict[str, str]:
        """
        Zalando uses highly predictable URL slugs for brands.
        We map every brand to BASE_URL to prevent BaseScraper's page.goto() 
        from crashing. We handle the true navigation inside scrape_brand_page.
        """
        matched = {}
        for fl_brand in freshlabels_brands:
            matched[fl_brand] = BASE_URL
            
        logger.info("[zalando] Mapped %d / %d Freshlabels brands", len(matched), len(freshlabels_brands))
        
        os.makedirs(RAW_DIR, exist_ok=True)
        with open(f"{RAW_DIR}/brand_id_map.json", "w", encoding="utf-8") as f:
            json.dump({b: _slugify(b) for b in matched}, f, ensure_ascii=False, indent=2)
            
        return matched

    # ------------------------------------------------------------------
    # Product scraping
    # ------------------------------------------------------------------
    
    async def _scroll_page(self, page: Page):
        """
        Scrolls down the page iteratively to trigger Zalando's lazy loading.
        """
        logger.debug("[zalando] Scrolling page to load all products...")
        previous_height = await page.evaluate("document.body.scrollHeight")
        
        # Max 10 scrolls per page to prevent infinite loops on massive catalogs
        for _ in range(10): 
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000) # Give React time to render new DOM nodes
            
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == previous_height:
                break # Reached the absolute bottom
            previous_height = new_height

    async def scrape_brand_page(self, page: Page, brand_name: str, url: str) -> list[dict]:
        """
        Manually overrides BaseScraper navigation to scrape BOTH women's and men's 
        catalogs for the specified brand.
        """
        products = []
        slug = _slugify(brand_name)
        urls_to_scrape = [
            f"{BASE_URL}/zeny/{slug}/",
            # f"{BASE_URL}/damske-obleceni/{slug}/",
            f"{BASE_URL}/panske-obleceni/{slug}/"
        ]
        
        scraped_at = datetime.now(timezone.utc).isoformat()
        
        # Zalando blocks bots heavily, so it helps to pretend we are Czech
        await page.set_extra_http_headers({'Accept-Language': 'cs-CZ,cs;q=0.9'})
        
        for target_url in urls_to_scrape:
            try:
                # Navigate specifically to the men's or women's brand page
                response = await page.goto(target_url, wait_until="domcontentloaded", timeout=20_000)
                
                # If the URL returns a 404 (e.g., brand doesn't have a men's line), skip gracefully
                if response and response.status == 404:
                    continue
                
                # Scroll down to trigger lazy loading of product cards
                await self._scroll_page(page) 
                
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                # Zalando product cards are wrapped in <article> tags
                cards = soup.find_all("article")
                logger.info("[zalando] Found %d product cards at %s", len(cards), target_url)
                
                for card in cards:
                    product = self._parse_card(card, brand_name, target_url, scraped_at)
                    if product:
                        products.append(product)
            except Exception as exc:
                logger.warning("[zalando] Failed to scrape %s: %s", target_url, exc)
                
        return products

    def _parse_card(self, card, brand_name: str, page_url: str, scraped_at: str) -> Optional[dict]:
        """Extract fields from a single Zalando product card."""
        # 1. Product URL
        a_tag = card.find("a", href=True)
        if not a_tag:
            return None
        href = a_tag["href"]
        product_url = href if href.startswith("http") else BASE_URL + href

        # 2. Product Name
        # Zalando puts the brand and the product name in sibling <h3> elements
        header_els = card.find_all("h3")
        product_name = ""
        for el in header_els:
            text = el.get_text(strip=True)
            if text and text.lower() != brand_name.lower():
                product_name = text
                break
        
        if not product_name:
            product_name = a_tag.get_text(strip=True)

        # 3. Prices
        price_texts = [
            span.get_text(strip=True) 
            for span in card.find_all(string=re.compile(r"Kč|CZK"))
        ]
        
        if not price_texts:
            return None
            
        prices = []
        for pt in price_texts:
            p = _parse_price(pt)
            if p:
                prices.append(p)
                
        original_price = None
        discounted_price = None
                
        if len(prices) == 1:
            original_price = prices[0]
        elif len(prices) >= 2:
            original_price = max(prices)
            discounted_price = min(prices)

        is_discounted = discounted_price is not None and discounted_price < original_price
        discount_pct = None
        if is_discounted and original_price > 0:
            discount_pct = round((original_price - discounted_price) / original_price * 100, 1)

        return {
            "product_name": product_name,
            "brand": brand_name,
            "price_czk": original_price,
            "discounted_price_czk": discounted_price,
            "is_discounted": is_discounted,
            "discount_pct": discount_pct,
            "url": product_url,
            "competitor": self.COMPETITOR_KEY,
            "scraped_at": scraped_at,
        }