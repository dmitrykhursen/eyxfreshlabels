"""
Paginate through a category listing and yield Product objects.
"""

import logging

from scraper import page_parser
from scraper.http_client import HttpClient, ScraperError
from scraper.models import Product

logger = logging.getLogger(__name__)


def scrape_category(
    category: dict,
    client: HttpClient,
    seen_urls: set,
    dry_run: bool = False,
) -> list:
    """
    Scrape all pages of a category and return a list of Products.

    :param category: dict with keys 'name' and 'url' from config.CATEGORIES
    :param client: HttpClient instance
    :param seen_urls: set of already-scraped product URLs (for resume)
    :param dry_run: if True, only collect URLs without fetching full pages
    :returns: list of Product objects (may be partial if SCRAPE_DETAIL_PAGES=False)
    """
    cat_name = category["name"]
    base_url = category["url"]
    products = []

    # Fetch page 1 to determine total page count
    logger.info("[%s] Fetching page 1: %s", cat_name, base_url)
    if dry_run:
        logger.info("[%s] DRY RUN — skipping HTTP requests", cat_name)
        return []

    try:
        html = client.get(base_url)
    except ScraperError as exc:
        logger.error("[%s] Failed to fetch page 1: %s", cat_name, exc)
        return []

    max_page = page_parser.extract_max_page(html)
    logger.info("[%s] Detected %s page(s)", cat_name, max_page)

    page_products = page_parser.extract_products_from_listing(html, cat_name)
    _collect(page_products, products, seen_urls, cat_name, 1)

    # Subsequent pages
    for page_num in range(2, max_page + 1):
        page_url = f"{base_url}?page={page_num}"
        logger.info("[%s] Fetching page %s/%s: %s", cat_name, page_num, max_page, page_url)
        try:
            html = client.get(page_url)
        except ScraperError as exc:
            logger.warning("[%s] Skipping page %s: %s", cat_name, page_num, exc)
            continue

        page_products = page_parser.extract_products_from_listing(html, cat_name)
        if not page_products:
            logger.info("[%s] No products on page %s — stopping early", cat_name, page_num)
            break
        _collect(page_products, products, seen_urls, cat_name, page_num)

    logger.info("[%s] Found %s new products", cat_name, len(products))
    return products


def _collect(
    page_products: list,
    accumulator: list,
    seen_urls: set,
    cat_name: str,
    page_num: int,
) -> None:
    for p in page_products:
        if p.url in seen_urls:
            logger.debug("[%s] Skip (already scraped): %s", cat_name, p.url)
            continue
        accumulator.append(p)
