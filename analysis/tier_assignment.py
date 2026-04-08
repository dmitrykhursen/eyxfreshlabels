"""
Step 0 — Brand Tier Assignment

Loads all Freshlabels scraped data, computes median price per brand,
assigns each to a price tier, saves data/analysis/brand_tier_mapping.csv.

Run standalone:
    python -m analysis.tier_assignment
"""

import glob
import os
import pandas as pd

TIER_THRESHOLDS = {
    "PREMIUM":        2500,
    "LIFESTYLE_CORE": 1800,
    "ENTRY":          1000,
    # below 1000 → BASICS
}

OUTPUT_PATH = "data/analysis/brand_tier_mapping.csv"
FRESHLABELS_GLOB = "output/products*.csv"


def assign_tier(median_price: float) -> str:
    if median_price >= TIER_THRESHOLDS["PREMIUM"]:
        return "PREMIUM"
    if median_price >= TIER_THRESHOLDS["LIFESTYLE_CORE"]:
        return "LIFESTYLE_CORE"
    if median_price >= TIER_THRESHOLDS["ENTRY"]:
        return "ENTRY"
    return "BASICS"


def load_freshlabels() -> pd.DataFrame:
    files = sorted(glob.glob(FRESHLABELS_GLOB))
    if not files:
        raise FileNotFoundError(f"No files matching {FRESHLABELS_GLOB}")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
    df = (
        df.sort_values("scraped_at", ascending=False)
        .drop_duplicates(subset="product_id", keep="first")
        .reset_index(drop=True)
    )
    return df


def build_tier_mapping(df: pd.DataFrame) -> pd.DataFrame:
    brand_stats = (
        df.groupby("brand")
        .agg(
            sku_count=("product_id", "size"),
            median_price_czk=("current_price", "median"),
        )
        .reset_index()
    )
    brand_stats["tier"] = brand_stats["median_price_czk"].apply(assign_tier)
    brand_stats = brand_stats.sort_values(["tier", "sku_count"], ascending=[True, False])
    brand_stats = brand_stats.rename(columns={"brand": "brand_name"})
    return brand_stats[["brand_name", "median_price_czk", "tier", "sku_count"]]


def run() -> pd.DataFrame:
    os.makedirs("data/analysis", exist_ok=True)
    df = load_freshlabels()
    mapping = build_tier_mapping(df)
    mapping.to_csv(OUTPUT_PATH, index=False)

    print(f"Brand tier mapping saved → {OUTPUT_PATH}")
    print(f"Total brands: {len(mapping)}, Total SKUs: {mapping['sku_count'].sum()}\n")

    summary = mapping.groupby("tier").agg(
        brands=("brand_name", "count"),
        skus=("sku_count", "sum"),
        median_price=("median_price_czk", "median"),
    )
    print(summary.to_string())
    return mapping


if __name__ == "__main__":
    run()
