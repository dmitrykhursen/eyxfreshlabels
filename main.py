"""
Freshlabels.cz web scraper — entry point.

Usage:
    python main.py [OPTIONS]

Options:
    --categories TEXT     Comma-separated category names to scrape
                          (default: all categories in config.py)
    --output-format TEXT  csv | json | both  (default: from config.py)
    --no-detail-pages     Skip product detail page scraping (faster)
    --resume              Skip URLs already recorded in state/scraped_urls.txt
    --dry-run             Print URLs that would be scraped without fetching

Examples:
    python main.py --dry-run
    python main.py --categories shoes --no-detail-pages
    python main.py --categories clothes_women,clothes_men --resume
    python main.py
"""

import argparse
import csv
import json
import logging
import os
import sys

from scraper import config
from scraper import category_scraper, product_scraper
from scraper.http_client import HttpClient
from scraper.models import Product

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_seen_urls() -> set:
    if not os.path.exists(config.STATE_FILE):
        return set()
    with open(config.STATE_FILE, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def record_url(url: str) -> None:
    os.makedirs(config.STATE_DIR, exist_ok=True)
    with open(config.STATE_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def init_csv() -> None:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(config.OUTPUT_CSV):
        with open(config.OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=Product.CSV_HEADERS)
            writer.writeheader()


def append_csv(product: Product) -> None:
    with open(config.OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=Product.CSV_HEADERS)
        writer.writerow(product.as_dict())


def write_json(products: list) -> None:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    data = [p.as_json_dict() for p in products]
    # If file exists, merge with existing records
    existing = []
    if os.path.exists(config.OUTPUT_JSON):
        try:
            with open(config.OUTPUT_JSON, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = []
    seen_ids = {r["product_id"] for r in existing}
    for rec in data:
        if rec["product_id"] not in seen_ids:
            existing.append(rec)
    with open(config.OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Scrape product data from freshlabels.cz",
    )
    parser.add_argument(
        "--categories",
        help="Comma-separated category names (default: all). "
             f"Available: {', '.join(c['name'] for c in config.CATEGORIES)}",
    )
    parser.add_argument(
        "--output-format",
        choices=["csv", "json", "both"],
        default=config.OUTPUT_FORMAT,
        help="Output format (default: %(default)s)",
    )
    parser.add_argument(
        "--no-detail-pages",
        action="store_true",
        help="Skip fetching product detail pages (faster, less data)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Skip URLs already in state/scraped_urls.txt (default: on)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore resume state and re-scrape everything",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print category URLs without making HTTP requests",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # Resolve categories
    all_categories = {c["name"]: c for c in config.CATEGORIES}
    if args.categories:
        names = [n.strip() for n in args.categories.split(",")]
        invalid = [n for n in names if n not in all_categories]
        if invalid:
            logger.error("Unknown categories: %s", ", ".join(invalid))
            logger.error("Available: %s", ", ".join(all_categories.keys()))
            sys.exit(1)
        selected = [all_categories[n] for n in names]
    else:
        selected = list(all_categories.values())

    scrape_detail = config.SCRAPE_DETAIL_PAGES and not args.no_detail_pages
    output_format = args.output_format
    use_resume    = args.resume and not args.no_resume

    if args.dry_run:
        logger.info("DRY RUN — printing category URLs (no HTTP requests)")
        for cat in selected:
            logger.info("  [%s] %s", cat["name"], cat["url"])
        return

    # Load resume state
    seen_urls = load_seen_urls() if use_resume else set()
    if seen_urls:
        logger.info("Resume: %s URLs already scraped", len(seen_urls))

    # Init output files
    if output_format in ("csv", "both"):
        init_csv()

    client = HttpClient()
    all_products: list[Product] = []

    for cat in selected:
        logger.info("=== Scraping category: %s ===", cat["name"])
        products = category_scraper.scrape_category(
            cat, client, seen_urls, dry_run=args.dry_run
        )

        for i, p in enumerate(products, 1):
            if scrape_detail:
                logger.info(
                    "[%s] Enriching product %s/%s: %s",
                    cat["name"], i, len(products), p.name or p.url,
                )
                product_scraper.enrich_product(p, client)

            # Write incrementally
            if output_format in ("csv", "both"):
                append_csv(p)
            all_products.append(p)
            record_url(p.url)
            seen_urls.add(p.url)

        logger.info("[%s] Done — %s products processed", cat["name"], len(products))

    # Final JSON write (all at once for valid JSON array)
    if output_format in ("json", "both"):
        write_json(all_products)
        logger.info("JSON saved to %s", config.OUTPUT_JSON)

    if output_format in ("csv", "both"):
        logger.info("CSV saved to %s", config.OUTPUT_CSV)

    logger.info("Finished. Total products this run: %s", len(all_products))


if __name__ == "__main__":
    main()
