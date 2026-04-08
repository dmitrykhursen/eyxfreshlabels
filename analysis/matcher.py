"""
Step 2 — Fuzzy product name matching.

Matches Freshlabels products against competitor products of the same brand
using normalised names + rapidfuzz.fuzz.token_sort_ratio.

Confidence tiers:
  HIGH:   score >= 90
  MEDIUM: score 80–89
  NO MATCH: score < 80
"""

import logging
import re
import unicodedata

import pandas as pd
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

HIGH_THRESHOLD   = 90
MEDIUM_THRESHOLD = 80

# Colour / size tokens to strip before comparison
_STRIP_PATTERN = re.compile(
    r"\s*[-/(\\[]\s*"
    r"(black|white|navy|grey|gray|green|red|blue|brown|beige|olive|ecru|sand|khaki|"
    r"pink|yellow|orange|purple|cream|natural|stone|charcoal|dark|light|"
    r"xxs|xs|s\b|m\b|l\b|xl\b|xxl\b|one\s+size|os\b|uni\b).*$",
    re.IGNORECASE,
)

_PUNCT = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")


def _normalise(name: str, brand: str) -> str:
    """
    Lowercase, remove brand prefix, strip colour/size suffix, remove punctuation.
    """
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower().strip()

    # Remove brand name prefix
    brand_lower = brand.lower().strip()
    if name.startswith(brand_lower):
        name = name[len(brand_lower):].strip(" -_:")

    # Strip colour/size suffix
    name = _STRIP_PATTERN.sub("", name)

    # Remove punctuation and normalise whitespace
    name = _PUNCT.sub(" ", name)
    name = _SPACES.sub(" ", name).strip()
    return name


def match_products(
    fl_df: pd.DataFrame,
    comp_df: pd.DataFrame,
    competitor_key: str,
) -> pd.DataFrame:
    """
    Match Freshlabels products against competitor products.

    Parameters
    ----------
    fl_df      : Freshlabels products with columns: product_id, name, brand, original_price, url
    comp_df    : Competitor products with columns: product_name, brand, price_czk, url, scraped_at
    competitor_key : e.g. "queens"

    Returns
    -------
    DataFrame with matched pairs and premium_pct.
    """
    results = []

    # Pre-compute normalised titles for competitor products per brand
    comp_df = comp_df.copy()
    comp_df["_norm"] = comp_df.apply(
        lambda r: _normalise(str(r["product_name"]), str(r["brand"])), axis=1
    )

    fl_df = fl_df.copy()
    fl_df["_norm"] = fl_df.apply(
        lambda r: _normalise(str(r["name"]), str(r["brand"])), axis=1
    )

    brands_in_both = set(fl_df["brand"].unique()) & set(comp_df["brand"].unique())
    logger.info(
        "[matcher] %d brands overlap between Freshlabels and %s",
        len(brands_in_both), competitor_key,
    )

    for brand in brands_in_both:
        fl_brand = fl_df[fl_df["brand"] == brand]
        comp_brand = comp_df[comp_df["brand"] == brand]

        if comp_brand.empty:
            continue

        comp_norms = comp_brand["_norm"].tolist()
        comp_indices = comp_brand.index.tolist()

        for _, fl_row in fl_brand.iterrows():
            fl_norm = fl_row["_norm"]
            if not fl_norm:
                continue

            # Find best match among competitor products of same brand
            result = process.extractOne(
                fl_norm,
                comp_norms,
                scorer=fuzz.token_sort_ratio,
            )
            if not result:
                continue

            score = result[1]
            match_idx_in_list = result[2]
            comp_idx = comp_indices[match_idx_in_list]
            comp_row = comp_brand.loc[comp_idx]

            if score < MEDIUM_THRESHOLD:
                continue

            confidence = "HIGH" if score >= HIGH_THRESHOLD else "MEDIUM"

            fl_price = fl_row.get("original_price") or fl_row.get("current_price")
            comp_price = comp_row["price_czk"]

            premium_pct = None
            if fl_price and comp_price and comp_price > 0:
                premium_pct = round((fl_price - comp_price) / comp_price * 100, 2)

            results.append({
                "brand": brand,
                "freshlabels_name": fl_row["name"],
                "freshlabels_price": fl_price,
                "freshlabels_url": fl_row.get("url", ""),
                f"{competitor_key}_name": comp_row["product_name"],
                f"{competitor_key}_price": comp_price,
                f"{competitor_key}_url": comp_row.get("url", ""),
                "premium_pct": premium_pct,
                "match_score": score,
                "match_confidence": confidence,
                "competitor": competitor_key,
                "scraped_at": comp_row.get("scraped_at", ""),
            })

    matched = pd.DataFrame(results)
    logger.info(
        "[matcher] %d matches (%d HIGH, %d MEDIUM) for %s",
        len(matched),
        (matched["match_confidence"] == "HIGH").sum() if not matched.empty else 0,
        (matched["match_confidence"] == "MEDIUM").sum() if not matched.empty else 0,
        competitor_key,
    )
    return matched


def match_rate_report(
    fl_df: pd.DataFrame,
    matched: pd.DataFrame,
    competitor_key: str,
) -> dict:
    """Return a dict with match rate statistics for the methodology section."""
    total = len(fl_df)
    if matched.empty:
        return {
            "competitor": competitor_key,
            "total_fl_products": total,
            "matched_high": 0,
            "matched_medium": 0,
            "unmatched": total,
            "match_rate_pct": 0.0,
        }
    high = (matched["match_confidence"] == "HIGH").sum()
    medium = (matched["match_confidence"] == "MEDIUM").sum()
    rate = round((high + medium) / total * 100, 1)
    return {
        "competitor": competitor_key,
        "total_fl_products": total,
        "matched_high": int(high),
        "matched_medium": int(medium),
        "unmatched": total - int(high + medium),
        "match_rate_pct": rate,
    }


def brand_match_report(
    fl_df: pd.DataFrame,
    matched: pd.DataFrame,
    comp_df: pd.DataFrame,
    competitor_key: str,
    tier_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Per-brand breakdown of match coverage.

    For every Freshlabels brand, shows:
      - fl_sku_count: total products on Freshlabels
      - comp_sku_count: products found on the competitor for this brand
      - found_on_competitor: True if brand appeared at all in scraped data
      - matched_high / matched_medium: product pairs above confidence threshold
      - unmatched_fl: FL products with no competitor match
      - match_rate_pct: (high + medium) / fl_sku_count * 100

    Brands not present on the competitor get zeros for all match columns.
    This is the primary "gap report" — shows exactly where coverage is strong
    or missing, per brand.
    """
    all_brands = fl_df["brand"].dropna().unique()

    # Count FL SKUs per brand
    fl_counts = fl_df.groupby("brand").size().rename("fl_sku_count")

    # Count competitor SKUs per brand
    comp_counts = (
        comp_df.groupby("brand").size().rename("comp_sku_count")
        if not comp_df.empty
        else pd.Series(dtype=int, name="comp_sku_count")
    )

    # Count matches per brand and confidence
    if not matched.empty:
        high_counts = (
            matched[matched["match_confidence"] == "HIGH"]
            .groupby("brand").size().rename("matched_high")
        )
        medium_counts = (
            matched[matched["match_confidence"] == "MEDIUM"]
            .groupby("brand").size().rename("matched_medium")
        )
    else:
        high_counts = pd.Series(dtype=int, name="matched_high")
        medium_counts = pd.Series(dtype=int, name="matched_medium")

    # Assemble into one dataframe
    report = (
        pd.DataFrame({"brand": all_brands})
        .set_index("brand")
        .join(fl_counts)
        .join(comp_counts)
        .join(high_counts)
        .join(medium_counts)
    )
    report = report.fillna(0).astype(int)
    report["found_on_competitor"] = report["comp_sku_count"] > 0
    report["matched_total"] = report["matched_high"] + report["matched_medium"]
    report["unmatched_fl"] = report["fl_sku_count"] - report["matched_total"]
    report["match_rate_pct"] = (
        report["matched_total"] / report["fl_sku_count"].replace(0, 1) * 100
    ).round(1)
    report["competitor"] = competitor_key

    if tier_map:
        report["tier"] = report.index.map(tier_map).fillna("UNKNOWN")

    report = report.reset_index().rename(columns={"brand": "brand_name"})

    # Sort: found brands first, then by match_rate desc, then alphabetically
    report = report.sort_values(
        ["found_on_competitor", "match_rate_pct", "brand_name"],
        ascending=[False, False, True],
    )
    return report


def unmatched_products(
    fl_df: pd.DataFrame,
    matched: pd.DataFrame,
    competitor_key: str,
) -> pd.DataFrame:
    """
    Return the Freshlabels products that had NO match on the competitor.
    Useful as an audit trail: "these specific products couldn't be compared."
    """
    if matched.empty:
        unmatched = fl_df.copy()
    else:
        matched_fl_names = set(matched["freshlabels_name"].str.lower())
        unmatched = fl_df[
            ~fl_df["name"].str.lower().isin(matched_fl_names)
        ].copy()

    unmatched["competitor"] = competitor_key
    return unmatched[["brand", "name", "original_price", "current_price", "url", "competitor"]]
