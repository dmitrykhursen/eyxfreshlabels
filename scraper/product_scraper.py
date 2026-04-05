"""
Fetch and enrich individual product detail pages.
Only called when config.SCRAPE_DETAIL_PAGES is True.
"""

import logging

from scraper import page_parser
from scraper.http_client import HttpClient, ScraperError
from scraper.models import Product

logger = logging.getLogger(__name__)


def enrich_product(product: Product, client: HttpClient) -> bool:
    """
    Fetch the product's detail page and merge extra data into the Product in-place.
    Returns True on success, False on failure (product is kept as-is on failure).
    """
    if not product.url:
        logger.warning("Product %s has no URL — skipping detail fetch", product.product_id)
        return False

    try:
        html = client.get(product.url)
    except ScraperError as exc:
        logger.warning("Failed to fetch detail for %s: %s", product.url, exc)
        return False

    page_parser.extract_product_detail(html, product)
    logger.debug("Enriched %s (%s)", product.name, product.product_id)
    return True
