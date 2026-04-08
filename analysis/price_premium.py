"""
Step 3 — Price premium calculation at 4 aggregation levels.

Reads:
  data/analysis/matched_pairs.csv
  data/analysis/brand_tier_mapping.csv
  output/products*.csv (for SKU weights)

Writes:
  data/analysis/per_product_premium.csv
  data/analysis/per_brand_premium.csv
  data/analysis/per_tier_premium.csv
  data/analysis/per_competitor_summary.csv
"""

import glob
import logging
import os

import pandas as pd

logger = logging.getLogger(__name__)

ANALYSIS_DIR = "data/analysis"


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    matched = pd.read_csv(f"{ANALYSIS_DIR}/matched_pairs.csv")
    tiers = pd.read_csv(f"{ANALYSIS_DIR}/brand_tier_mapping.csv")

    fl_files = sorted(glob.glob("output/products*.csv"))
    fl_df = pd.concat([pd.read_csv(f) for f in fl_files], ignore_index=True)
    fl_df["scraped_at"] = pd.to_datetime(fl_df["scraped_at"], errors="coerce")
    fl_df = fl_df.sort_values("scraped_at", ascending=False).drop_duplicates(
        subset="product_id", keep="first"
    )
    sku_counts = fl_df.groupby("brand").size().rename("fl_sku_count")
    return matched, tiers, sku_counts


def _tier_order(tier: str) -> int:
    return {"PREMIUM": 0, "LIFESTYLE_CORE": 1, "ENTRY": 2, "BASICS": 3}.get(tier, 4)


def compute_all() -> dict[str, pd.DataFrame]:
    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    matched, tiers, sku_counts = _load_inputs()

    tier_map = tiers.set_index("brand_name")["tier"].to_dict()

    # -- Level 1: per_product --------------------------------------------------
    per_product = matched.copy()
    per_product["tier"] = per_product["brand"].map(tier_map).fillna("UNKNOWN")
    per_product.to_csv(f"{ANALYSIS_DIR}/per_product_premium.csv", index=False)
    logger.info("Saved per_product_premium.csv (%d rows)", len(per_product))

    # -- Level 2: per_brand ----------------------------------------------------
    per_brand = (
        per_product.groupby(["brand", "tier", "competitor"])
        .agg(
            mean_premium=("premium_pct", "mean"),
            median_premium=("premium_pct", "median"),
            std_premium=("premium_pct", "std"),
            n_matched=("premium_pct", "count"),
        )
        .round(2)
        .reset_index()
    )
    per_brand["fl_sku_count"] = per_brand["brand"].map(sku_counts)
    per_brand["tier_order"] = per_brand["tier"].apply(_tier_order)
    per_brand = per_brand.sort_values(["tier_order", "fl_sku_count"], ascending=[True, False])
    per_brand.drop(columns="tier_order", inplace=True)
    per_brand.to_csv(f"{ANALYSIS_DIR}/per_brand_premium.csv", index=False)
    logger.info("Saved per_brand_premium.csv (%d rows)", len(per_brand))

    # -- Level 3: per_tier  (the key strategic output) -------------------------
    per_tier = (
        per_product.groupby(["tier", "competitor"])
        .agg(
            mean_premium=("premium_pct", "mean"),
            median_premium=("premium_pct", "median"),
            std_premium=("premium_pct", "std"),
            n_products=("premium_pct", "count"),
            n_brands=("brand", "nunique"),
        )
        .round(2)
        .reset_index()
    )
    per_tier["tier_order"] = per_tier["tier"].apply(_tier_order)
    per_tier = per_tier.sort_values("tier_order").drop(columns="tier_order")
    per_tier.to_csv(f"{ANALYSIS_DIR}/per_tier_premium.csv", index=False)
    logger.info("Saved per_tier_premium.csv (%d rows)", len(per_tier))

    # -- Level 4: per_competitor summary ---------------------------------------
    rows = []
    for comp in per_product["competitor"].unique():
        comp_df = per_product[per_product["competitor"] == comp]
        simple_mean = comp_df["premium_pct"].mean()

        # Weighted mean: weight by Freshlabels SKU count of the brand
        comp_df2 = comp_df.copy()
        comp_df2["weight"] = comp_df2["brand"].map(sku_counts).fillna(1)
        weighted_mean = (
            (comp_df2["premium_pct"] * comp_df2["weight"]).sum()
            / comp_df2["weight"].sum()
        )
        rows.append({
            "competitor": comp,
            "overall_mean_premium": round(simple_mean, 2),
            "weighted_mean_premium": round(weighted_mean, 2),
            "n_brands_matched": comp_df["brand"].nunique(),
            "n_products_matched": len(comp_df),
        })

    per_comp = pd.DataFrame(rows)
    per_comp.to_csv(f"{ANALYSIS_DIR}/per_competitor_summary.csv", index=False)
    logger.info("Saved per_competitor_summary.csv")

    return {
        "per_product": per_product,
        "per_brand": per_brand,
        "per_tier": per_tier,
        "per_competitor": per_comp,
    }


def run() -> None:
    results = compute_all()
    print("\n=== Per-Tier Premium (strategic summary) ===")
    print(results["per_tier"].to_string(index=False))
    print("\n=== Per-Competitor Summary ===")
    print(results["per_competitor"].to_string(index=False))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
