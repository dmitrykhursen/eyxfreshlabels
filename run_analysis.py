"""
Analysis pipeline orchestrator.

Runs the full pipeline in order:
  Step 0: Tier assignment
  Step 1: Load scraped competitor data
  Step 2: Fuzzy product matching
  Step 3: Price premium calculation

Usage:
    python run_analysis.py
    python run_analysis.py --competitors queens
    python run_analysis.py --confidence high   # only HIGH-confidence matches
"""

import argparse
import glob
import logging
import os
import sys

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_analysis")


def load_freshlabels() -> pd.DataFrame:
    files = sorted(glob.glob("output/products*.csv"))
    if not files:
        logger.error("No output/products*.csv found.")
        sys.exit(1)
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
    df = df.sort_values("scraped_at", ascending=False).drop_duplicates(
        subset="product_id", keep="first"
    ).reset_index(drop=True)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the price premium analysis pipeline.")
    parser.add_argument(
        "--competitors",
        default="",
        help="Comma-separated competitors to include (default: all with scraped data)",
    )
    parser.add_argument(
        "--confidence",
        choices=["all", "high"],
        default="all",
        help="Match confidence filter for premium calculation (default: all)",
    )
    args = parser.parse_args()

    os.makedirs("data/analysis", exist_ok=True)

    # ── Step 0: Tier assignment ───────────────────────────────────────────────
    logger.info("=== Step 0: Brand tier assignment ===")
    from analysis.tier_assignment import run as run_tiers
    tier_mapping = run_tiers()

    # ── Step 1: Load competitor data ──────────────────────────────────────────
    logger.info("=== Step 1: Loading competitor data ===")
    comp_filter = [c.strip() for c in args.competitors.split(",") if c.strip()]

    comp_files = sorted(glob.glob("data/competitors/*/all_products.csv"))
    if not comp_files:
        logger.error("No competitor data found in data/competitors/. Run run_scraping.py first.")
        sys.exit(1)

    all_comp_dfs = []
    for path in comp_files:
        competitor = path.split(os.sep)[-2]
        if comp_filter and competitor not in comp_filter:
            continue
        df = pd.read_csv(path)
        if df.empty:
            logger.warning("[%s] Empty competitor file: %s", competitor, path)
            continue
        logger.info("[%s] Loaded %d products from %s", competitor, len(df), path)
        all_comp_dfs.append(df)

    if not all_comp_dfs:
        logger.error("No usable competitor data found.")
        sys.exit(1)

    comp_all = pd.concat(all_comp_dfs, ignore_index=True)

    # ── Step 2: Fuzzy matching ────────────────────────────────────────────────
    logger.info("=== Step 2: Fuzzy product matching ===")
    from analysis.matcher import match_products, match_rate_report, brand_match_report, unmatched_products

    fl_df = load_freshlabels()
    tier_map = tier_mapping.set_index("brand_name")["tier"].to_dict()

    all_matched = []
    match_reports = []
    all_brand_reports = []

    for competitor in comp_all["competitor"].unique():
        comp_df = comp_all[comp_all["competitor"] == competitor]
        logger.info("[matcher] Matching vs %s (%d products)", competitor, len(comp_df))

        matched = match_products(fl_df, comp_df, competitor)

        if args.confidence == "high":
            matched = matched[matched["match_confidence"] == "HIGH"]

        if not matched.empty:
            all_matched.append(matched)

        # Overall match rate (for methodology section)
        report = match_rate_report(fl_df, matched, competitor)
        match_reports.append(report)
        logger.info(
            "[matcher] %s: %d HIGH + %d MEDIUM matches (%.1f%% match rate)",
            competitor, report["matched_high"], report["matched_medium"], report["match_rate_pct"],
        )

        # Per-brand match report (the key gap report)
        brand_report = brand_match_report(fl_df, matched, comp_df, competitor, tier_map)
        all_brand_reports.append(brand_report)

        # Log a clear summary: found vs not found vs matched
        found = brand_report[brand_report["found_on_competitor"]]
        not_found = brand_report[~brand_report["found_on_competitor"]]
        logger.info(
            "[matcher] %s brand coverage: %d found, %d NOT on competitor",
            competitor, len(found), len(not_found),
        )
        if not not_found.empty:
            logger.info(
                "[matcher] Brands NOT on %s: %s",
                competitor,
                ", ".join(not_found["brand_name"].tolist()),
            )
        low_match = found[found["match_rate_pct"] < 20]
        if not low_match.empty:
            logger.info(
                "[matcher] Brands found but <20%% product match on %s: %s",
                competitor,
                ", ".join(
                    f"{r['brand_name']} ({r['match_rate_pct']:.0f}%)"
                    for _, r in low_match.iterrows()
                ),
            )

        # Save unmatched products list
        unmatched = unmatched_products(fl_df, matched, competitor)
        unmatched_path = f"data/analysis/unmatched_products_{competitor}.csv"
        unmatched.to_csv(unmatched_path, index=False)
        logger.info(
            "[matcher] %d unmatched FL products saved → %s",
            len(unmatched), unmatched_path,
        )

    if not all_matched:
        logger.warning("No matched product pairs found. Check scraped data and matching thresholds.")
        pd.DataFrame().to_csv("data/analysis/matched_pairs.csv", index=False)
        pd.DataFrame(match_reports).to_csv("data/analysis/match_rate_report.csv", index=False)
        if all_brand_reports:
            pd.concat(all_brand_reports).to_csv("data/analysis/brand_match_report.csv", index=False)
        sys.exit(0)

    matched_all = pd.concat(all_matched, ignore_index=True)
    matched_all["tier"] = matched_all["brand"].map(tier_map).fillna("UNKNOWN")

    matched_all.to_csv("data/analysis/matched_pairs.csv", index=False)
    pd.DataFrame(match_reports).to_csv("data/analysis/match_rate_report.csv", index=False)
    pd.concat(all_brand_reports).to_csv("data/analysis/brand_match_report.csv", index=False)
    logger.info("Matched pairs saved → data/analysis/matched_pairs.csv (%d rows)", len(matched_all))
    logger.info("Brand match report → data/analysis/brand_match_report.csv")

    # ── Step 3: Price premium ─────────────────────────────────────────────────
    logger.info("=== Step 3: Price premium calculation ===")
    from analysis.price_premium import run as run_premium
    run_premium()

    logger.info("=== Analysis complete. Run 'streamlit run dashboard_extended.py' ===")


if __name__ == "__main__":
    main()
