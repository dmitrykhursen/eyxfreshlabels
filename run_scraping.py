"""
Competitor scraping orchestrator.

Usage:
    python run_scraping.py                                    # scrape all registered competitors
    python run_scraping.py --competitors queens               # single competitor
    python run_scraping.py --competitors queens --brands patagonia,carhartt-wip  # brand subset

Adding a new competitor later:
    1. Create scrapers/{name}_scraper.py extending BaseScraper
    2. Add it to COMPETITOR_REGISTRY below
    3. Run: python run_scraping.py --competitors {name}
"""

import argparse
import asyncio
import csv
import glob
import json
import logging
import os
import sys

import pandas as pd

# ── Competitor registry ──────────────────────────────────────────────────────
# To add a competitor: import its scraper class and add an entry here.
from scrapers.queens_scraper import QueensScraper
from scrapers.nila_scraper import NilaScraper
from scrapers.zalando_scraper import ZalandoScraper

COMPETITOR_REGISTRY = {
    "queens":  QueensScraper,
    "nila":    NilaScraper,
    # "footshop": FootshopScraper,
    # "zoot":     ZootScraper,
    "zalando":  ZalandoScraper,
    # "aboutyou": AboutYouScraper,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_scraping")


def load_freshlabels_brands(brand_filter: list[str] | None = None) -> list[str]:
    """Load all unique brand names from Freshlabels scraped data."""
    files = sorted(glob.glob("output/products*.csv"))
    if not files:
        logger.error("No output/products*.csv found. Run the Freshlabels scraper first.")
        sys.exit(1)
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.drop_duplicates(subset="product_id")
    all_brands = sorted(df["brand"].dropna().unique().tolist())
    if brand_filter:
        # Allow partial / case-insensitive matching for CLI convenience
        lower_filter = [b.lower() for b in brand_filter]
        all_brands = [b for b in all_brands if b.lower() in lower_filter]
        if not all_brands:
            logger.error("No matching brands found for filter: %s", brand_filter)
            sys.exit(1)
    logger.info("Loaded %d Freshlabels brands to search for", len(all_brands))
    return all_brands


def save_products(products: list[dict], competitor: str) -> str:
    """Save scraped products to CSV and return the path."""
    out_dir = f"data/competitors/{competitor}"
    os.makedirs(out_dir, exist_ok=True)
    path = f"{out_dir}/all_products.csv"

    if not products:
        logger.warning("[%s] No products scraped — output file will be empty.", competitor)
        pd.DataFrame().to_csv(path, index=False)
        return path

    df = pd.DataFrame(products)
    df.to_csv(path, index=False)
    logger.info("[%s] Saved %d products → %s", competitor, len(products), path)
    return path


def save_exclusivity(
    presence: dict[str, bool],
    competitor: str,
    freshlabels_brands: list[str],
) -> None:
    """Save brand exclusivity map."""
    os.makedirs("data/competitors", exist_ok=True)
    excl_path = "data/competitors/brand_exclusivity.csv"

    # Load existing exclusivity file if it exists (to merge with prior competitors)
    if os.path.exists(excl_path):
        excl_df = pd.read_csv(excl_path)
    else:
        excl_df = pd.DataFrame({"brand_name": freshlabels_brands})

    excl_df[f"on_{competitor}"] = excl_df["brand_name"].map(
        lambda b: presence.get(b, False)
    )

    # Update exclusivity score = number of known competitors that DON'T carry the brand
    competitor_cols = [c for c in excl_df.columns if c.startswith("on_")]
    excl_df["exclusivity_score"] = excl_df[competitor_cols].apply(
        lambda row: sum(1 for v in row if v is False or v == False), axis=1  # noqa: E712
    )
    excl_df.to_csv(excl_path, index=False)
    logger.info("Exclusivity map saved → %s", excl_path)


async def run_competitor(
    competitor_key: str,
    freshlabels_brands: list[str],
    headless: bool = True,
) -> None:
    ScraperClass = COMPETITOR_REGISTRY[competitor_key]
    scraper = ScraperClass(headless=headless)

    await scraper.launch()
    try:
        brand_url_map = await scraper.discover_brands(freshlabels_brands)
        if not brand_url_map:
            logger.warning("[%s] No brands matched — nothing to scrape.", competitor_key)
            return

        products, presence = await scraper.scrape_all_brands(brand_url_map, freshlabels_brands)
        save_products(products, competitor_key)
        save_exclusivity(presence, competitor_key, freshlabels_brands)

        logger.info(
            "[%s] Done. %d products, %d/%d brands present.",
            competitor_key, len(products), sum(presence.values()), len(freshlabels_brands),
        )
    finally:
        await scraper.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape competitor product prices.")
    parser.add_argument(
        "--competitors",
        default=",".join(COMPETITOR_REGISTRY.keys()),
        help="Comma-separated list of competitors to scrape (default: all registered)",
    )
    parser.add_argument(
        "--brands",
        default="",
        help="Comma-separated brand name filter (default: all Freshlabels brands)",
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run browser in visible mode (non-headless) for debugging",
    )
    args = parser.parse_args()

    competitors = [c.strip() for c in args.competitors.split(",") if c.strip()]
    brand_filter = [b.strip() for b in args.brands.split(",") if b.strip()] if args.brands else None

    unknown = [c for c in competitors if c not in COMPETITOR_REGISTRY]
    if unknown:
        logger.error("Unknown competitors: %s. Available: %s", unknown, list(COMPETITOR_REGISTRY.keys()))
        sys.exit(1)

    brands = load_freshlabels_brands(brand_filter)

    for competitor in competitors:
        logger.info("=== Scraping: %s ===", competitor)
        asyncio.run(run_competitor(competitor, brands, headless=not args.visible))

    logger.info("All done. Run 'python run_analysis.py' next.")


if __name__ == "__main__":
    main()
