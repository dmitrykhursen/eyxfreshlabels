"""
Parses Freshlabels HTML pages.

Primary strategy: extract structured product data from the window.dataLayer
JSON embedded in every listing page. Fallback to CSS selectors if needed.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

from scraper import config
from scraper.models import Product

logger = logging.getLogger(__name__)

# Regex to locate the start of each dataLayer.push( call.
# We then use balanced-brace parsing to extract the full JSON argument.
_DATALAYER_PUSH_RE = re.compile(r"dataLayer\.push\s*\(")


def extract_products_from_listing(html: str, category_name: str) -> list:
    """
    Parse a category listing page and return a list of partial Product objects.
    Data comes from the dataLayer JSON embedded in <script> tags.
    Falls back to CSS-selector parsing if dataLayer is absent.
    """
    soup = BeautifulSoup(html, "lxml")
    products = _parse_datalayer(soup, category_name)
    if not products:
        logger.debug("dataLayer parse yielded nothing — trying CSS fallback")
        products = _parse_listing_css(soup, category_name)
    return products


def extract_max_page(html: str) -> int:
    """Return the last page number found in pagination links, or 1."""
    soup = BeautifulSoup(html, "lxml")
    max_page = 1
    # Pagination links contain ?page=N
    for a in soup.select("a[href*='?page='], a[href*='&page=']"):
        href = a.get("href", "")
        m = re.search(r"[?&]page=(\d+)", href)
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page


def extract_product_detail(html: str, product: Product) -> None:
    """
    Enrich a Product in-place using data from its detail page.
    Extracts: sizes_in_stock, all colors, all image_urls, descriptions.
    Merges with existing data — does not overwrite non-empty fields from listing.
    """
    soup = BeautifulSoup(html, "lxml")

    # Try JSON-LD schema.org Product first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") == "Product":
                _apply_jsonld(data, product)
                break
            # Sometimes it's a list
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        _apply_jsonld(item, product)
                        break
        except (json.JSONDecodeError, AttributeError):
            continue

    # Sizes — buttons/links that represent size options
    sizes = []
    for el in soup.select("[data-size], .size-option, .product-size"):
        text = el.get_text(strip=True)
        if text and text not in sizes:
            sizes.append(text)
    # Also try select elements
    for option in soup.select("select[name*='size'] option, select[name*='variant'] option"):
        text = option.get_text(strip=True)
        val = option.get("value", "")
        if text and text.lower() not in ("", "choose size", "select size", "--"):
            # Prefer attribute that signals availability
            disabled = option.has_attr("disabled")
            if not disabled and text not in sizes:
                sizes.append(text)
    if sizes and not product.sizes_in_stock:
        product.sizes_in_stock = sizes

    # Colors
    colors = []
    for el in soup.select("[data-color], .color-option, .product-color"):
        text = el.get("data-color") or el.get_text(strip=True)
        if text and text not in colors:
            colors.append(text)
    if colors and not product.colors:
        product.colors = colors

    # Images — Cloudinary CDN URLs
    images = []
    for img in soup.select("img[src*='cloudinary'], img[data-src*='cloudinary']"):
        src = img.get("data-src") or img.get("src", "")
        if src and src not in images:
            images.append(src)
    if images:
        product.image_urls = images  # replace with full gallery from detail page


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_datalayer(soup: BeautifulSoup, category_name: str) -> list:
    """Extract products from dataLayer.push calls in <script> tags.

    Freshlabels uses:  dataLayer.push({..., "impression": {"products": [...]}})
    A single <script> block may contain multiple push() calls, so we locate
    each one individually and use balanced-brace parsing to extract the JSON.
    """
    products = []
    now = datetime.now(timezone.utc).isoformat()

    for script in soup.find_all("script"):
        text = script.string
        if not text or "impression" not in text:
            continue

        for match in _DATALAYER_PUSH_RE.finditer(text):
            data = _extract_json_arg(text, match.end())
            if data is None:
                continue

            impression_products = (
                data.get("impression", {}).get("products")
                or data.get("ecommerce", {}).get("impressions")
                or []
            )
            for item in impression_products:
                p = _impression_to_product(item, category_name, now)
                if p:
                    products.append(p)

    return products


def _extract_json_arg(text: str, start: int) -> Optional[dict]:
    """Starting after 'dataLayer.push(', find the opening '{' and walk to its
    balanced closing '}', then parse the result as JSON."""
    brace_start = text.find("{", start)
    if brace_start == -1:
        return None
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[brace_start: i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _impression_to_product(item: dict, category_name: str, scraped_at: str) -> Optional[Product]:
    """Convert a single dataLayer impression dict into a Product."""
    product_id = str(item.get("id", item.get("item_id", ""))).strip()
    name       = str(item.get("name", item.get("item_name", ""))).strip()
    brand      = str(item.get("brand", item.get("item_brand", ""))).strip()
    url_path   = str(item.get("url", "")).strip()
    if not url_path.startswith("http"):
        url_path = config.BASE_URL + url_path

    # Prices — dataLayer uses various field names across site versions
    current_price  = _to_float(item.get("pocketPrice") or item.get("price") or item.get("item_price"))
    original_price = _to_float(item.get("fullPrice") or item.get("original_price"))
    discount_pct: Optional[float] = None
    if current_price and original_price and original_price > 0:
        discount_pct = round((1 - current_price / original_price) * 100, 1)

    category_path = str(item.get("category", item.get("item_category", ""))).strip()
    color         = str(item.get("color", item.get("item_variant", ""))).strip()
    image         = str(item.get("image", "")).strip()
    raw_labels    = str(item.get("labels", "")).strip()

    if not product_id and not name:
        return None

    p = Product(
        product_id=product_id,
        url=url_path,
        category=category_name,
        category_path=category_path,
        name=name,
        brand=brand,
        current_price=current_price,
        original_price=original_price,
        discount_pct=discount_pct,
        scraped_at=scraped_at,
    )
    if color:
        p.colors = [color]
    if image:
        p.image_urls = [image]
    if raw_labels:
        p.split_labels(raw_labels)

    return p


def _apply_jsonld(data: dict, product: Product) -> None:
    """Merge schema.org JSON-LD Product data into an existing Product."""
    if not product.name:
        product.name = data.get("name", "")
    if not product.brand:
        brand_field = data.get("brand", {})
        product.brand = brand_field.get("name", "") if isinstance(brand_field, dict) else str(brand_field)
    if not product.image_urls:
        imgs = data.get("image", [])
        if isinstance(imgs, str):
            imgs = [imgs]
        product.image_urls = imgs

    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if offers and not product.current_price:
        product.current_price = _to_float(offers.get("price"))


def _parse_listing_css(soup: BeautifulSoup, category_name: str) -> list:
    """
    CSS-selector fallback for listing pages.
    Covers common Freshlabels product card selectors; update if site changes.
    """
    products = []
    now = datetime.now(timezone.utc).isoformat()

    for card in soup.select(".product-item, .product-card, [data-product-id]"):
        product_id = card.get("data-product-id", "")
        name_el    = card.select_one(".product-name, .product-title, h2, h3")
        brand_el   = card.select_one(".product-brand, .brand")
        price_el   = card.select_one(".price-current, .price, [data-price]")
        img_el     = card.select_one("img")
        link_el    = card.select_one("a[href]")

        name  = name_el.get_text(strip=True) if name_el else ""
        brand = brand_el.get_text(strip=True) if brand_el else ""
        url   = config.BASE_URL + link_el["href"] if link_el else ""
        image = ""
        if img_el:
            image = img_el.get("data-src") or img_el.get("src", "")

        price_text = price_el.get_text(strip=True) if price_el else ""
        current_price = _parse_price_text(price_text)

        if not name and not product_id:
            continue

        p = Product(
            product_id=product_id,
            url=url,
            category=category_name,
            category_path="",
            name=name,
            brand=brand,
            current_price=current_price,
            original_price=None,
            discount_pct=None,
            scraped_at=now,
        )
        if image:
            p.image_urls = [image]
        products.append(p)

    return products


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _parse_price_text(text: str) -> Optional[float]:
    """Extract numeric price from strings like '1 190 Kč' or '€ 49.99'."""
    cleaned = re.sub(r"[^\d.,]", "", text.replace("\xa0", ""))
    return _to_float(cleaned) if cleaned else None
