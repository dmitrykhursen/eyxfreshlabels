"""
Price Premium tab for the Freshlabels dashboard.

Self-contained module. Import and call render() from dashboard_extended.py:

    from dashboard.tabs.price_premium import render
    with tab_price_premium:
        render()
"""

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ANALYSIS_DIR = "data/analysis"
EXCL_PATH = "data/competitors/brand_exclusivity.csv"
PLOTLY_TEMPLATE = "plotly_white"
COLOR_PALETTE = px.colors.qualitative.Set2

TIER_ORDER = ["PREMIUM", "LIFESTYLE_CORE", "ENTRY", "BASICS"]
COMPETITOR_COLORS = {
    "queens":   "#e63946",
    "nila":     "#2a9d8f",
    "footshop": "#457b9d",
    "zoot":     "#e9c46a",
    "zalando":  "#f4a261",
    "aboutyou": "#264653",
}


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def _load(path: str) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    return df if not df.empty else None


def _load_all() -> dict:
    data = {
        "per_product":    _load(f"{ANALYSIS_DIR}/per_product_premium.csv"),
        "per_brand":      _load(f"{ANALYSIS_DIR}/per_brand_premium.csv"),
        "per_tier":       _load(f"{ANALYSIS_DIR}/per_tier_premium.csv"),
        "per_comp":       _load(f"{ANALYSIS_DIR}/per_competitor_summary.csv"),
        "match_report":   _load(f"{ANALYSIS_DIR}/match_rate_report.csv"),
        "brand_coverage": _load(f"{ANALYSIS_DIR}/brand_match_report.csv"),
        "tiers":          _load(f"{ANALYSIS_DIR}/brand_tier_mapping.csv"),
        "exclusivity":    _load(EXCL_PATH),
    }
    # Attach per-competitor unmatched product files dynamically
    data["unmatched"] = {}
    import glob as _glob
    for path in _glob.glob(f"{ANALYSIS_DIR}/unmatched_products_*.csv"):
        competitor = path.split("unmatched_products_")[-1].replace(".csv", "")
        data["unmatched"][competitor] = _load(path)
    return data


# ── Main render function ──────────────────────────────────────────────────────

def render() -> None:
    data = _load_all()

    if data["per_product"] is None:
        st.info(
            "No price premium data yet. Run the pipeline first:\n\n"
            "```bash\n"
            "# 1. Install dependencies\n"
            "pip install playwright rapidfuzz && playwright install chromium\n\n"
            "# 2. Scrape competitor data\n"
            "python run_scraping.py --competitors queens\n\n"
            "# 3. Run analysis\n"
            "python run_analysis.py\n"
            "```"
        )
        return

    pp = data["per_product"]
    competitors = sorted(pp["competitor"].unique())

    st.markdown(
        "**How Freshlabels' prices compare to competitors for the same products.** "
        "Products are matched by brand and fuzzy product name, then original (non-discounted) prices are compared. "
        "A positive premium means Freshlabels charges more; negative means cheaper."
    )
    st.caption(
        "**Abbreviations & key terms** — "
        "**FL** / Freshlabels: the Freshlabels.cz catalog (our side of the comparison). "
        "**SKU** (Stock Keeping Unit): one product as it appears in the catalog. "
        "**Premium %**: (FL price − competitor price) / competitor price × 100. "
        "Positive = FL is more expensive; negative = FL is cheaper. "
        "**Match Rate %**: share of FL products for a given brand that were successfully paired with a competitor product. "
        "**Confidence HIGH / MEDIUM**: quality of the fuzzy name match — "
        "HIGH = score ≥ 90 (near-identical name after normalisation), "
        "MEDIUM = score 80–89 (likely same product, possible variant difference). "
        "Matches with a price gap > ±20% are automatically discarded as likely false positives. "
        "**Tiers** (based on brand median price on Freshlabels): "
        "PREMIUM ≥ 2 500 CZK · LIFESTYLE_CORE 1 800–2 499 CZK · ENTRY 1 000–1 799 CZK · BASICS < 1 000 CZK. "
        "**Exclusivity Score**: number of scraped competitors that do NOT carry a given brand "
        "(max = total number of competitors scraped). Higher = more exclusive to Freshlabels."
    )
    st.divider()

    # ── Section 1: Headline scorecard ────────────────────────────────────────
    st.subheader("Headline: Price Premium vs Competitors")
    st.caption(
        # "Weighted mean premium across all matched product pairs for each competitor. "
        "Overall mean premium across all matched products "

        "Positive = Freshlabels charges MORE than the competitor. "
        "Based on original (non-discounted) prices, matched products only."
    )

    comp_summary = data["per_comp"]
    cols = st.columns(max(len(competitors), 1))
    for i, comp in enumerate(competitors):
        row = comp_summary[comp_summary["competitor"] == comp]
        if row.empty:
            cols[i].metric(comp.title(), "n/a")
            continue
        # val = row["weighted_mean_premium"].iloc[0]
        val = row["overall_mean_premium"].iloc[0]
        
        n = int(row["n_products_matched"].iloc[0])
        delta_color = "normal" if val >= 0 else "inverse"
        cols[i].metric(
            comp.title(),
            f"{val:+.1f}%",
            delta=f"based on {n:,} products",
            delta_color=delta_color,
        )

    st.divider()

    # ── Section 1b: Brand Coverage ────────────────────────────────────────────
    st.subheader("Brand Coverage — Which Brands Are Found on Each Competitor?")
    st.caption(
        "Shows how many Freshlabels brands appear on each competitor site "
        "and how many products were successfully matched per brand. "
        "**FL SKUs**: total products on Freshlabels for that brand. "
        "**Competitor SKUs**: total products scraped for that brand on the competitor. "
        "**Match Rate %**: (HIGH + MEDIUM matches) / FL SKUs × 100. "
        "Brands with 0 competitor SKUs were not found on that competitor at all. "
        "The right-hand chart shows brands absent from a competitor — "
        "these are potential Freshlabels exclusives."
    )

    brand_cov = data["brand_coverage"]
    if brand_cov is not None:
        for comp in competitors:
            comp_cov = brand_cov[brand_cov["competitor"] == comp].copy()
            if comp_cov.empty:
                continue

            found = comp_cov[comp_cov["found_on_competitor"]]
            not_found = comp_cov[~comp_cov["found_on_competitor"]]

            m1, m2, m3 = st.columns(3)
            m1.metric(f"{comp.title()} — Brands Found", len(found))
            m2.metric("Brands NOT Found", len(not_found))
            m3.metric(
                "Avg Match Rate (found brands)",
                f"{found['match_rate_pct'].mean():.1f}%" if not found.empty else "n/a",
            )

            col_left, col_right = st.columns(2)

            with col_left:
                if not found.empty:
                    found_sorted = found.sort_values("match_rate_pct", ascending=True)
                    fig_found = px.bar(
                        found_sorted,
                        x="match_rate_pct",
                        y="brand_name",
                        orientation="h",
                        color="match_rate_pct",
                        color_continuous_scale="RdYlGn",
                        range_color=[0, 100],
                        title=f"Brands Found on {comp.title()} — Product Match Rate",
                        labels={"match_rate_pct": "Match Rate %", "brand_name": ""},
                        hover_data=["fl_sku_count", "comp_sku_count", "matched_total", "unmatched_fl"],
                        template=PLOTLY_TEMPLATE,
                    )
                    fig_found.update_layout(
                        height=max(300, len(found_sorted) * 22),
                        coloraxis_showscale=False,
                        yaxis=dict(categoryorder="total ascending"),
                    )
                    st.plotly_chart(fig_found, use_container_width=True)
                else:
                    st.info(f"No Freshlabels brands found on {comp.title()}.")

            with col_right:
                if not not_found.empty:
                    tier_col = "tier" if "tier" in not_found.columns else None
                    fig_missing = px.bar(
                        not_found.sort_values("fl_sku_count", ascending=True),
                        x="fl_sku_count",
                        y="brand_name",
                        orientation="h",
                        color=tier_col,
                        title=f"Brands NOT on {comp.title()} (by FL SKU count)",
                        labels={"fl_sku_count": "FL SKUs", "brand_name": ""},
                        color_discrete_sequence=COLOR_PALETTE,
                        template=PLOTLY_TEMPLATE,
                    )
                    fig_missing.update_layout(
                        height=max(300, len(not_found) * 22),
                        yaxis=dict(categoryorder="total ascending"),
                    )
                    st.plotly_chart(fig_missing, use_container_width=True)
                else:
                    st.success(f"All Freshlabels brands were found on {comp.title()}.")

            with st.expander(f"Full brand breakdown — {comp.title()}"):
                display_cov = comp_cov[[
                    "brand_name", "tier", "fl_sku_count", "comp_sku_count",
                    "matched_high", "matched_medium", "matched_total",
                    "unmatched_fl", "match_rate_pct", "found_on_competitor",
                ] if "tier" in comp_cov.columns else [
                    "brand_name", "fl_sku_count", "comp_sku_count",
                    "matched_high", "matched_medium", "matched_total",
                    "unmatched_fl", "match_rate_pct", "found_on_competitor",
                ]].sort_values(["found_on_competitor", "match_rate_pct"], ascending=[False, False])

                def _cov_color(val):
                    if isinstance(val, bool):
                        return "background-color: #d4edda" if val else "background-color: #f8d7da"
                    return ""

                st.dataframe(
                    display_cov.reset_index(drop=True),
                    column_config={
                        "brand_name": "Brand",
                        "tier": "Tier",
                        "fl_sku_count": st.column_config.NumberColumn("FL SKUs", format="%d"),
                        "comp_sku_count": st.column_config.NumberColumn("Competitor SKUs", format="%d"),
                        "matched_high": st.column_config.NumberColumn("HIGH matches", format="%d"),
                        "matched_medium": st.column_config.NumberColumn("MEDIUM matches", format="%d"),
                        "matched_total": st.column_config.NumberColumn("Total matched", format="%d"),
                        "unmatched_fl": st.column_config.NumberColumn("Unmatched FL", format="%d"),
                        "match_rate_pct": st.column_config.NumberColumn("Match Rate %", format="%.1f%%"),
                        "found_on_competitor": st.column_config.CheckboxColumn("Found?"),
                    },
                    use_container_width=True,
                    hide_index=True,
                )
    else:
        st.warning("Brand coverage data not available. Run run_analysis.py first.")

    st.divider()

    # ── Section 2: Brand × Competitor heatmap ───────────────────────────────
    st.subheader("Brand × Competitor Price Premium Heatmap")
    st.caption(
        "Each cell = mean Premium % for that brand–competitor pair (matched products only). "
        "Green = Freshlabels charges more; red = competitor charges more; '–' = no matched products. "
        "Rows are sorted by price tier (top = most premium) then by SKU count within each tier. "
        "**Tier definitions** (by brand median price on Freshlabels): "
        "PREMIUM ≥ 2 500 CZK · LIFESTYLE_CORE 1 800–2 499 CZK · ENTRY 1 000–1 799 CZK · BASICS < 1 000 CZK."
    )

    brand_comp = data["per_brand"]
    tiers_df = data["tiers"]
    if brand_comp is not None and tiers_df is not None:
        tier_map = tiers_df.set_index("brand_name")["tier"].to_dict()
        sku_map  = tiers_df.set_index("brand_name")["sku_count"].to_dict()

        pivot = brand_comp.pivot_table(
            index="brand", columns="competitor", values="mean_premium", aggfunc="mean"
        )

        # Sort: tier order first, then SKU count descending within tier
        pivot["_tier"] = pivot.index.map(tier_map)
        pivot["_sku"]  = pivot.index.map(sku_map)
        pivot["_tier_order"] = pivot["_tier"].map(
            {"PREMIUM": 0, "LIFESTYLE_CORE": 1, "ENTRY": 2, "BASICS": 3}
        ).fillna(4)
        pivot = pivot.sort_values(["_tier_order", "_sku"], ascending=[True, False])
        pivot = pivot.drop(columns=["_tier", "_sku", "_tier_order"])

        # Build tier label annotations
        tier_labels = [tier_map.get(b, "") for b in pivot.index]

        fig = go.Figure(
            data=go.Heatmap(
                z=pivot.values,
                x=list(pivot.columns),
                y=list(pivot.index),
                colorscale="RdYlGn",
                zmid=0,
                text=[[f"{v:+.1f}%" if pd.notna(v) else "–" for v in row] for row in pivot.values],
                texttemplate="%{text}",
                hovertemplate="Brand: %{y}<br>Competitor: %{x}<br>Premium: %{text}<extra></extra>",
                colorbar=dict(title="Premium %"),
            )
        )
        fig.update_layout(
            title="Price Premium % (green = Freshlabels charges more)",
            xaxis_title="",
            yaxis_title="",
            height=max(400, len(pivot) * 22),
            template=PLOTLY_TEMPLATE,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Tier legend
        tier_counts = pd.Series(tier_labels).value_counts()
        for tier in TIER_ORDER:
            if tier in tier_counts:
                st.caption(f"**{tier}**: {tier_counts[tier]} brands in this tier")
    else:
        st.warning("Brand-level data not available.")

    st.divider()

    # ── Section 3: Tier breakdown ─────────────────────────────────────────────
    st.subheader("Price Premium by Price Tier")
    st.caption(
        "The key strategic question: where is Freshlabels' pricing power concentrated? "
        "**Tier assignment** is based on the brand's median price across all its FL products: "
        "**PREMIUM** ≥ 2 500 CZK (e.g. Arc'teryx, Canada Goose) · "
        "**LIFESTYLE_CORE** 1 800–2 499 CZK (e.g. Patagonia, Carhartt WIP) · "
        "**ENTRY** 1 000–1 799 CZK (e.g. Vans, New Balance apparel) · "
        "**BASICS** < 1 000 CZK. "
        "Bars above 0% = Freshlabels is priced higher than the competitor in that tier."
    )

    per_tier = data["per_tier"]
    if per_tier is not None:
        per_tier["tier"] = pd.Categorical(per_tier["tier"], categories=TIER_ORDER, ordered=True)
        per_tier = per_tier.sort_values("tier")

        fig = px.bar(
            per_tier,
            x="tier",
            y="mean_premium",
            color="competitor",
            barmode="group",
            title="Mean Price Premium by Tier and Competitor",
            labels={"mean_premium": "Mean Premium (%)", "tier": "Price Tier", "competitor": "Competitor"},
            color_discrete_map=COMPETITOR_COLORS,
            template=PLOTLY_TEMPLATE,
            hover_data=["n_products", "n_brands"],
        )
        fig.add_hline(y=0, line_dash="dash", line_color="black", line_width=1)
        fig.add_annotation(
            text="Positive = Freshlabels charges more",
            xref="paper", yref="paper", x=0.01, y=0.99,
            showarrow=False, font=dict(size=11, color="gray"),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            per_tier[["tier", "competitor", "mean_premium", "median_premium", "n_products", "n_brands"]],
            column_config={
                "tier": "Tier",
                "competitor": "Competitor",
                "mean_premium": st.column_config.NumberColumn("Mean Premium %", format="%+.2f%%"),
                "median_premium": st.column_config.NumberColumn("Median Premium %", format="%+.2f%%"),
                "n_products": st.column_config.NumberColumn("# Matched Products", format="%d"),
                "n_brands": st.column_config.NumberColumn("# Brands", format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("Tier-level data not available.")

    st.divider()

    # ── Section 4: Exclusivity analysis ─────────────────────────────────────
    st.subheader("Brand Exclusivity — Freshlabels' Curation Moat")
    st.caption(
        "**Exclusivity Score** = number of scraped competitors that do NOT carry the brand. "
        "Maximum score = total number of competitors scraped. "
        "A brand with the maximum score is not found on any competitor — "
        "customers who want it must come to Freshlabels. "
        "This is the 'curation moat': Freshlabels' ability to stock brands unavailable elsewhere."
    )

    excl_df = data["exclusivity"]
    if excl_df is not None and "exclusivity_score" in excl_df.columns:
        comp_cols = [c for c in excl_df.columns if c.startswith("on_")]
        n_comps = len(comp_cols)

        excl_df = excl_df.copy()
        if tiers_df is not None:
            excl_df["tier"] = excl_df["brand_name"].map(
                tiers_df.set_index("brand_name")["tier"].to_dict()
            ).fillna("UNKNOWN")

        fully_excl = excl_df[excl_df["exclusivity_score"] == n_comps]
        st.info(
            f"**{len(fully_excl)} of {len(excl_df)} Freshlabels brands "
            f"({len(fully_excl)/len(excl_df)*100:.0f}%) are not found on any of the "
            f"{n_comps} benchmarked competitor(s).** "
            "These exclusive brands represent Freshlabels' strongest curation moat — "
            "customers who want them have no alternative."
        )

        excl_sorted = excl_df.sort_values("exclusivity_score", ascending=False).head(30)
        fig = px.bar(
            excl_sorted,
            x="exclusivity_score",
            y="brand_name",
            orientation="h",
            color="tier" if "tier" in excl_sorted.columns else None,
            title=f"Top 30 Most Exclusive Brands (max score = {n_comps})",
            labels={"exclusivity_score": "# Competitors NOT carrying this brand", "brand_name": ""},
            color_discrete_sequence=COLOR_PALETTE,
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Exclusivity data not available. Run run_scraping.py first.")

    st.divider()

    # ── Section 5: Matched products table ────────────────────────────────────
    st.subheader("Matched Products — Price Comparison Detail")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        sel_comp = st.multiselect("Competitor", competitors, default=competitors, key="pp_comp")
    with c2:
        all_brands = sorted(pp["brand"].unique())
        sel_brands = st.multiselect("Brand", all_brands, default=all_brands, key="pp_brand")
    with c3:
        all_tiers = [t for t in TIER_ORDER if t in pp.get("tier", pd.Series()).unique()]
        if "tier" in pp.columns:
            sel_tiers = st.multiselect("Tier", TIER_ORDER, default=TIER_ORDER, key="pp_tier")
        else:
            sel_tiers = TIER_ORDER
    with c4:
        conf_filter = st.radio("Confidence", ["All", "HIGH only"], horizontal=True, key="pp_conf")

    table_df = pp.copy()
    if sel_comp:
        table_df = table_df[table_df["competitor"].isin(sel_comp)]
    if sel_brands:
        table_df = table_df[table_df["brand"].isin(sel_brands)]
    if "tier" in table_df.columns and sel_tiers:
        table_df = table_df[table_df["tier"].isin(sel_tiers)]
    if conf_filter == "HIGH only":
        table_df = table_df[table_df["match_confidence"] == "HIGH"]

    st.caption(f"{len(table_df):,} matched pairs")

    # Build generic comp_name / comp_price columns by reading the per-row competitor column.
    # This works for any number of competitors dynamically.
    def _pick_col(row, suffix):
        comp = row.get("competitor", "")
        col = f"{comp}{suffix}"
        if col in row.index:
            return row[col]
        return None

    table_df = table_df.copy()
    table_df["comp_name"]  = table_df.apply(lambda r: _pick_col(r, "_name"),  axis=1)
    table_df["comp_price"] = table_df.apply(lambda r: _pick_col(r, "_price"), axis=1)

    display_cols = [
        "brand",
        "freshlabels_name", "freshlabels_price",
        "comp_name", "comp_price",
        "premium_pct", "match_score", "match_confidence", "competitor",
    ]
    display_cols = [c for c in display_cols if c in table_df.columns]

    def _premium_color(val):
        if pd.isna(val):
            return ""
        color = "#d4edda" if val >= 0 else "#f8d7da"
        return f"background-color: {color}"

    styled = (
        table_df[display_cols]
        .reset_index(drop=True)
        .style.map(_premium_color, subset=["premium_pct"] if "premium_pct" in display_cols else [])
    )

    col_config = {
        "brand": "Brand",
        "freshlabels_name": st.column_config.TextColumn("Freshlabels Product", width="large"),
        "freshlabels_price": st.column_config.NumberColumn("FL Price (CZK)", format="%.0f"),
        "comp_name":  st.column_config.TextColumn("Competitor Product", width="large"),
        "comp_price": st.column_config.NumberColumn("Competitor Price (CZK)", format="%.0f"),
        "premium_pct": st.column_config.NumberColumn("Premium %", format="%+.1f%%"),
        "match_score": st.column_config.NumberColumn("Match Score", format="%.0f"),
        "match_confidence": "Confidence",
        "competitor": "Competitor",
    }

    st.dataframe(styled, column_config=col_config, use_container_width=True,
                 hide_index=True, height=500)

    st.divider()

    # ── Section 6: Methodology ───────────────────────────────────────────────
    with st.expander("Methodology & Data Quality"):
        st.markdown(
            "**Pricing principle:** Original (non-discounted) prices are used on both sides. "
            "Discounted prices reflect short-term promotions, not structural brand value.\n\n"
            "**Matching pipeline:**\n"
            "1. Products are matched only within the same brand.\n"
            "2. Names are normalised: lowercased, brand prefix removed, "
            "colour/size suffix stripped (e.g. `- Black`, `/ S`), punctuation removed.\n"
            "3. Best-match is found using `rapidfuzz.fuzz.token_set_ratio` — "
            "this handles cases where a competitor prepends a category or appends a colour "
            "to the model name (the FL name is a *subset* of the competitor name).\n"
            "4. **Price sanity filter**: pairs where `|Premium %| > 20%` are discarded "
            "as likely false positives — a genuine same-product match should not have "
            "prices more than 20% apart.\n\n"
            "| Confidence | Fuzzy Score | Interpretation |\n"
            "|---|---|---|\n"
            "| HIGH | ≥ 90 | Near-identical name — same product with high certainty |\n"
            "| MEDIUM | 80–89 | Likely same product, possible colour/size variant in the name |\n"
            "| — (excluded) | < 80 | Names too different to be reliably matched |\n\n"
            "**Known limitations:** fuzzy name matching cannot distinguish between "
            "products with very similar names but different specifications "
            "(e.g. different fabric weights). The ±20% price filter removes the worst "
            "false positives but does not catch all edge cases."
        )

        match_report = data["match_report"]
        if match_report is not None:
            st.markdown("**Match rates per competitor:**")
            st.dataframe(
                match_report,
                column_config={
                    "competitor": "Competitor",
                    "total_fl_products": st.column_config.NumberColumn("FL Products", format="%d"),
                    "matched_high": st.column_config.NumberColumn("HIGH matches", format="%d"),
                    "matched_medium": st.column_config.NumberColumn("MEDIUM matches", format="%d"),
                    "unmatched": st.column_config.NumberColumn("Unmatched", format="%d"),
                    "match_rate_pct": st.column_config.NumberColumn("Match Rate %", format="%.1f%%"),
                },
                use_container_width=True,
                hide_index=True,
            )
            low_rate = match_report[match_report["match_rate_pct"] < 15]
            if not low_rate.empty:
                st.warning(
                    f"Low match rate (< 15%) for: {', '.join(low_rate['competitor'].tolist())}. "
                    "This may indicate poor brand overlap or a scraping issue."
                )

        st.markdown(
            "**Queens.cz note:** Queens is a subsidiary of Footshop Group (acquired 2021). "
            "If prices converge strongly with a future Footshop scrape, treat them as one "
            "benchmark rather than two independent data points."
        )
