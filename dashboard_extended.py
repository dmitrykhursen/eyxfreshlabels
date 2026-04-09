"""
Freshlabels.cz — Brand as an Asset Dashboard (Extended)

Extends the original product analytics with case-study-aligned sections:
brand equity signals, LTV vs CAC modelling, and price-premium analysis.

Run with:  streamlit run dashboard_extended.py
"""

import glob
import sys
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Make sure dashboard/ package is importable
sys.path.insert(0, os.path.dirname(__file__))
from dashboard.tabs.price_premium import render as render_competitor_premium

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Freshlabels — Brand as an Asset",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
    initial_sidebar_state="expanded",
)

COLOR_PALETTE = px.colors.qualitative.Set2
PLOTLY_TEMPLATE = "plotly_white"

# Baseline economic parameters from the case study
BASELINE = {
    "aov": 2200,              # Average Order Value (CZK)
    "conv_rate": 1.5,         # Conversion rate (%)
    "pno": 10.0,              # Share of marketing cost in turnover (%)
    "gross_margin": 40.0,     # Gross margin (%)
    "repeat_rate": 25.0,      # Repeat purchase rate in 12 months (%)
    "nonpaid_share": 40.0,    # Share of non-paid traffic (%)
    "paid_share": 60.0,       # Share of paid traffic (%)
    "orders_per_year": 1.3,   # Avg purchases per customer per year
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data
def load_data() -> pd.DataFrame:
    csv_files = sorted(glob.glob("output/products*.csv"))
    if not csv_files:
        st.error("No CSV files found in output/ directory. Run the scraper first.")
        st.stop()

    dfs = [pd.read_csv(f) for f in csv_files]
    df = pd.concat(dfs, ignore_index=True)

    df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
    df = (
        df.sort_values("scraped_at", ascending=False)
        .drop_duplicates(subset="product_id", keep="first")
        .reset_index(drop=True)
    )

    df["has_discount"] = df["discount_pct"].fillna(0) > 0
    df["has_sustainability"] = df["sustainability_labels"].fillna("").str.len() > 0
    df["main_category"] = (
        df["category_path"].fillna("").apply(lambda x: x.split(" > ")[0] if x else "Unknown")
    )
    df["sub_category"] = (
        df["category_path"].fillna("").apply(lambda x: x.split(" > ")[-1] if x else "Unknown")
    )

    # Price premium — % above/below category (main_category) average
    cat_means = df.groupby("main_category")["current_price"].transform("mean")
    df["price_premium_pct"] = (df["current_price"] - cat_means) / cat_means * 100

    return df


def explode_pipe(series: pd.Series) -> pd.Series:
    return (
        series.dropna()
        .astype(str)
        .str.split("|")
        .explode()
        .str.strip()
        .pipe(lambda s: s[s != ""])
        .pipe(lambda s: s[s.str.lower() != "none"])
    )


def clean_sizes(series: pd.Series) -> pd.Series:
    return (
        explode_pipe(series)
        .str.replace(r"\s*last chance to buy.*", "", regex=True)
        .str.strip()
    )


def hhi_index(shares: pd.Series) -> float:
    """Herfindahl-Hirschman Index (0-10000) — brand market concentration."""
    return float(((shares / shares.sum()) ** 2).sum() * 10000)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df_all = load_data()

# ---------------------------------------------------------------------------
# Sidebar — filters + case study parameters
# ---------------------------------------------------------------------------
st.sidebar.header("Catalog Filters")

categories = sorted(df_all["category"].unique())
sel_categories = st.sidebar.multiselect("Category", categories, default=categories)

main_cats = sorted(df_all["main_category"].unique())
sel_main_cats = st.sidebar.multiselect(
    "Product Family", main_cats, default=main_cats,
    help="Top-level grouping from category path",
)

brands = sorted(df_all["brand"].dropna().unique())
sel_brands = st.sidebar.multiselect("Brand", brands, default=brands)

price_min = float(df_all["current_price"].min())
price_max = float(df_all["current_price"].max())
sel_price = st.sidebar.slider(
    "Price range (CZK)",
    min_value=price_min, max_value=price_max,
    value=(price_min, price_max), step=10.0,
)

only_discounted = st.sidebar.checkbox("Only discounted")
only_sustainable = st.sidebar.checkbox("Only sustainable")

df = df_all.copy()
df = df[df["category"].isin(sel_categories)]
df = df[df["main_category"].isin(sel_main_cats)]
df = df[df["brand"].isin(sel_brands)]
df = df[df["current_price"].between(sel_price[0], sel_price[1])]
if only_discounted:
    df = df[df["has_discount"]]
if only_sustainable:
    df = df[df["has_sustainability"]]

st.sidebar.divider()
st.sidebar.caption(f"Showing **{len(df):,}** of {len(df_all):,} products")

st.sidebar.divider()
st.sidebar.header("Business Model Inputs")
st.sidebar.caption("Baselines from the case study — adjust to test scenarios")

aov = st.sidebar.number_input("AOV — Avg Order Value (CZK)", 500, 10000, BASELINE["aov"], 50)
conv_rate = st.sidebar.number_input("Conversion Rate (%)", 0.1, 10.0, BASELINE["conv_rate"], 0.1)
gross_margin = st.sidebar.number_input("Gross Margin (%)", 10.0, 80.0, BASELINE["gross_margin"], 1.0)
pno = st.sidebar.number_input("PNO — Marketing % of Turnover", 1.0, 40.0, BASELINE["pno"], 0.5)
repeat_rate = st.sidebar.number_input("Repeat Purchase Rate (%)", 0.0, 100.0, BASELINE["repeat_rate"], 1.0)
orders_per_year = st.sidebar.number_input("Orders / year (brand cust.)", 1.0, 5.0, BASELINE["orders_per_year"], 0.1)
nonpaid_share = st.sidebar.slider("Non-Paid Traffic Share (%)", 0, 100, int(BASELINE["nonpaid_share"]), 1)

# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------
st.title("Freshlabels — Brand as an Asset")
st.caption("Interactive dashboard combining scraped catalog data with the brand-equity business model")

if df.empty:
    st.warning("No products match current filters. Adjust the sidebar.")
    st.stop()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_overview, tab_brand_portfolio, tab_pricing, tab_equity, tab_ltv, tab_premium, tab_comp_premium, tab_explorer = st.tabs([
    "Overview",
    "Brand Portfolio",
    "Pricing & Discounts",
    "Brand Equity Signals",
    "LTV vs CAC Model",
    "Catalog Price Premium",
    "Competitor Price Premium",
    "Product Explorer",
])

# =============================================================================
# TAB 1: OVERVIEW
# =============================================================================
with tab_overview:
    st.markdown(
        "**High-level snapshot of the Freshlabels catalog** as scraped. "
        "All counts and prices reflect the latest scrape after de-duplication (one row per `product_id`). "
        "Use the sidebar filters to narrow by category, brand, or price range."
    )
    st.caption(
        "**Glossary** — "
        "**CZK**: Czech Koruna (currency). "
        "**On Sale**: product has a recorded discount (original price > current price). "
        "**Product Family**: the first segment of the full category path "
        "(e.g. `Clothing > Jackets > Fleece` → Product Family = *Clothing*). "
        "**Promo Tags**: labels like *New*, *Bestseller*, *Limited edition* assigned by the Freshlabels site. "
        "**Sustainability Labels**: certifications or eco-labels attached to a product (e.g. *Fair Trade*, *GOTS*, *Recycled*)."
    )
    st.divider()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Products", f"{len(df):,}")
    c2.metric("Brands", df["brand"].nunique())
    c3.metric("Subcategories", df["category_path"].nunique())
    c4.metric("Avg Price", f"{df['current_price'].mean():,.0f} CZK")
    c5.metric("On Sale", f"{df['has_discount'].mean()*100:.1f}%")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        cat_counts = df["category"].value_counts().reset_index()
        cat_counts.columns = ["Category", "Count"]
        fig = px.pie(cat_counts, names="Category", values="Count",
                     title="Products by Category",
                     color_discrete_sequence=COLOR_PALETTE, template=PLOTLY_TEMPLATE)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        main_counts = df["main_category"].value_counts().head(15).reset_index()
        main_counts.columns = ["Product Family", "Count"]
        fig = px.bar(main_counts, x="Count", y="Product Family", orientation="h",
                     title="Top Product Families",
                     color_discrete_sequence=COLOR_PALETTE, template=PLOTLY_TEMPLATE)
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig, use_container_width=True)

    fig = px.histogram(df, x="current_price", color="category", nbins=40,
                       title="Price Distribution by Category",
                       labels={"current_price": "Price (CZK)"},
                       color_discrete_sequence=COLOR_PALETTE, template=PLOTLY_TEMPLATE)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        promo = explode_pipe(df["promo_tags"])
        if not promo.empty:
            pc = promo.value_counts().head(10).reset_index()
            pc.columns = ["Tag", "Count"]
            fig = px.bar(pc, x="Count", y="Tag", orientation="h",
                         title="Most Common Promo Tags",
                         color_discrete_sequence=COLOR_PALETTE, template=PLOTLY_TEMPLATE)
            fig.update_layout(yaxis=dict(categoryorder="total ascending"))
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        sust = explode_pipe(df["sustainability_labels"])
        if not sust.empty:
            sc = sust.value_counts().reset_index()
            sc.columns = ["Label", "Count"]
            fig = px.bar(sc, x="Count", y="Label", orientation="h",
                         title="Sustainability Labels",
                         color_discrete_sequence=[COLOR_PALETTE[2]], template=PLOTLY_TEMPLATE)
            fig.update_layout(yaxis=dict(categoryorder="total ascending"))
            st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# TAB 2: BRAND PORTFOLIO
# =============================================================================
with tab_brand_portfolio:
    st.markdown(
        "**Brand-level breakdown of the Freshlabels catalog.** "
        "Each metric aggregates all products belonging to a brand within the current filters."
    )
    st.caption(
        "**Glossary** — "
        "**HHI** (Herfindahl-Hirschman Index): market concentration measure. "
        "Computed as Σ(brand_share²) × 10 000. "
        "0 = perfectly fragmented; 10 000 = single brand monopoly. "
        "Thresholds: < 1 500 = competitive, 1 500–2 500 = moderate, > 2 500 = concentrated. "
        "**Share %**: brand's share of total product count in the filtered catalog. "
        "**Breadth**: number of distinct Product Families the brand covers — higher = wider assortment. "
        "**% Sustainable**: share of the brand's products that carry at least one sustainability label. "
        "**Premium vs cat %**: average price premium of the brand's products vs the mean price in their Product Family "
        "(positive = brand charges above the family average, negative = below). "
        "**% on Sale**: share of the brand's products currently discounted."
    )
    st.divider()
    # Compute brand-level KPIs
    brand_kpi = df.groupby("brand").agg(
        products=("product_id", "size"),
        avg_price=("current_price", "mean"),
        median_price=("current_price", "median"),
        avg_discount=("discount_pct", "mean"),
        discount_rate=("has_discount", lambda x: x.mean() * 100),
        sust_rate=("has_sustainability", lambda x: x.mean() * 100),
        breadth=("main_category", "nunique"),
        premium_pct=("price_premium_pct", "mean"),
    ).round(2).sort_values("products", ascending=False).reset_index()
    brand_kpi["share_pct"] = (brand_kpi["products"] / brand_kpi["products"].sum() * 100).round(2)

    c1, c2, c3, c4 = st.columns(4)
    total_brands = brand_kpi["brand"].nunique()
    hhi = hhi_index(brand_kpi.set_index("brand")["products"])
    top3_share = brand_kpi["share_pct"].head(3).sum()
    top10_share = brand_kpi["share_pct"].head(10).sum()
    c1.metric("Brands", f"{total_brands}")
    c2.metric("HHI (concentration)", f"{hhi:.0f}", help="0 = perfect competition, 10000 = monopoly. <1500 = competitive, >2500 = concentrated")
    c3.metric("Top 3 share", f"{top3_share:.1f}%")
    c4.metric("Top 10 share", f"{top10_share:.1f}%")

    st.divider()
    top_n = st.slider("Show top N brands", 5, min(40, total_brands), 20)
    top_brands = brand_kpi.head(top_n)

    # Products per brand
    fig = px.bar(top_brands, x="brand", y="products",
                 title=f"Products per Brand (top {top_n})",
                 labels={"brand": "Brand", "products": "# Products"},
                 color="avg_price", color_continuous_scale="Blues",
                 template=PLOTLY_TEMPLATE)
    st.plotly_chart(fig, use_container_width=True)

    # Brand price box plot
    fig = px.box(df[df["brand"].isin(top_brands["brand"])],
                 x="brand", y="current_price",
                 title=f"Price Distribution by Brand (top {top_n})",
                 labels={"current_price": "Price (CZK)", "brand": "Brand"},
                 template=PLOTLY_TEMPLATE)
    order = top_brands.sort_values("median_price", ascending=False)["brand"].tolist()
    fig.update_layout(xaxis=dict(categoryorder="array", categoryarray=order))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(top_brands.sort_values("sust_rate", ascending=True),
                     x="sust_rate", y="brand", orientation="h",
                     title="Sustainability Rate by Brand (%)",
                     labels={"sust_rate": "% of products with sustainability labels", "brand": ""},
                     color_discrete_sequence=[COLOR_PALETTE[2]], template=PLOTLY_TEMPLATE)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(top_brands.sort_values("breadth", ascending=True),
                     x="breadth", y="brand", orientation="h",
                     title="Assortment Breadth (# product families)",
                     labels={"breadth": "# distinct product families", "brand": ""},
                     color_discrete_sequence=[COLOR_PALETTE[0]], template=PLOTLY_TEMPLATE)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Brand Portfolio Table")
    st.dataframe(
        brand_kpi,
        column_config={
            "brand": "Brand",
            "products": st.column_config.NumberColumn("# Products", format="%d"),
            "share_pct": st.column_config.NumberColumn("Share %", format="%.2f%%"),
            "avg_price": st.column_config.NumberColumn("Avg Price (CZK)", format="%.0f"),
            "median_price": st.column_config.NumberColumn("Median Price", format="%.0f"),
            "avg_discount": st.column_config.NumberColumn("Avg Discount", format="%.1f%%"),
            "discount_rate": st.column_config.NumberColumn("% on Sale", format="%.1f%%"),
            "sust_rate": st.column_config.NumberColumn("% Sustainable", format="%.1f%%"),
            "breadth": st.column_config.NumberColumn("Breadth", format="%d"),
            "premium_pct": st.column_config.NumberColumn("Premium vs cat %", format="%.1f%%"),
        },
        use_container_width=True, hide_index=True, height=400,
    )

# =============================================================================
# TAB 3: PRICING & DISCOUNTS
# =============================================================================
with tab_pricing:
    st.markdown(
        "**Pricing structure and discount behaviour across the catalog.** "
        "Discount metrics are computed only on products that are currently discounted "
        "(original price > current price). The sustainability premium section tests whether "
        "eco-labelled products are priced higher than conventional ones within the same catalog."
    )
    st.caption(
        "**Glossary** — "
        "**Avg Discount**: mean discount percentage among discounted products only (excludes full-price items). "
        "**Median Price**: the middle price value — less sensitive to outliers than the mean. "
        "**% on Sale**: share of ALL catalog products (including filters) that have any active discount. "
        "**Diagonal (y = x)**: the dashed reference line in the scatter plot where current price = original price "
        "(i.e. no discount). Points below the line are on sale. "
        "**Sustainable / Conventional**: products are labelled *Sustainable* if they carry at least one "
        "sustainability label; all others are *Conventional*."
    )
    st.divider()
    discounted = df[df["has_discount"]]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg Discount", f"{discounted['discount_pct'].mean():.1f}%" if not discounted.empty else "n/a")
    c2.metric("Max Discount", f"{discounted['discount_pct'].max():.1f}%" if not discounted.empty else "n/a")
    c3.metric("Median Price", f"{df['current_price'].median():,.0f} CZK")
    c4.metric("% on Sale", f"{df['has_discount'].mean()*100:.1f}%")

    st.divider()
    scat = df.dropna(subset=["current_price", "original_price"])
    fig = px.scatter(scat, x="original_price", y="current_price",
                     color="discount_pct", color_continuous_scale="RdYlGn_r",
                     hover_data=["name", "brand"],
                     title="Current vs Original Price — color by discount %",
                     labels={"original_price": "Original (CZK)", "current_price": "Current (CZK)", "discount_pct": "Discount %"},
                     template=PLOTLY_TEMPLATE)
    max_v = max(scat["original_price"].max(), scat["current_price"].max())
    fig.add_trace(go.Scatter(x=[0, max_v], y=[0, max_v], mode="lines",
                             line=dict(dash="dash", color="gray"), name="No discount (y=x)"))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        if not discounted.empty:
            fig = px.histogram(discounted, x="discount_pct", nbins=25,
                               title="Discount % Distribution",
                               labels={"discount_pct": "Discount (%)"},
                               color_discrete_sequence=[COLOR_PALETTE[1]], template=PLOTLY_TEMPLATE)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        if not discounted.empty:
            top_sub = discounted["sub_category"].value_counts().head(12).index
            fig = px.box(discounted[discounted["sub_category"].isin(top_sub)],
                         x="sub_category", y="discount_pct",
                         title="Discount by Subcategory (top 12)",
                         labels={"sub_category": "", "discount_pct": "Discount %"},
                         template=PLOTLY_TEMPLATE)
            fig.update_xaxes(tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)

    # Sustainability premium
    st.divider()
    sust_df = df.copy()
    sust_df["Segment"] = sust_df["has_sustainability"].map({True: "Sustainable", False: "Conventional"})
    fig = px.box(sust_df, x="Segment", y="current_price", color="Segment",
                 title="Do Sustainable Products Command a Premium?",
                 labels={"current_price": "Price (CZK)"},
                 color_discrete_sequence=[COLOR_PALETTE[2], COLOR_PALETTE[7]],
                 template=PLOTLY_TEMPLATE)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    display_cols = ["name", "brand", "category_path", "current_price", "original_price", "discount_pct"]
    with c1:
        st.markdown("**Top 10 Most Expensive**")
        st.dataframe(df.nlargest(10, "current_price")[display_cols].reset_index(drop=True),
                     use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Top 10 Cheapest**")
        st.dataframe(df.nsmallest(10, "current_price")[display_cols].reset_index(drop=True),
                     use_container_width=True, hide_index=True)

# =============================================================================
# TAB 4: BRAND EQUITY SIGNALS
# =============================================================================
with tab_equity:
    st.markdown(
        "**Proxies for brand equity observable from the catalog.** "
        "A strong brand typically shows: large assortment share, wide category breadth, "
        "consistent sustainability positioning, and lower reliance on discounting."
    )
    st.caption(
        "**Composite Brand Equity Score (0–100)** — weighted sum of five min-max normalised signals: "
        "30% Assortment Share (more products = more customer exposure), "
        "25% Category Breadth (wider = brand is versatile), "
        "20% Inverse Discount Dependency (less discounting = stronger pricing power), "
        "15% Sustainability Share (eco-credentials signal premium positioning), "
        "10% Price Premium vs Product Family (positive premium confirms customers pay above average). "
        "All components are normalised to 0–100 within the currently filtered brand set — "
        "scores are relative, not absolute. "
        "**Strategic Quadrant axes**: X = Assortment Share (% of total catalog products), "
        "Y = Price Premium vs Product Family average (%). "
        "Dot size = number of products; colour = % of products on sale "
        "(red = high discount dependency = weaker equity signal). "
        "The vertical dashed line marks the median assortment share; horizontal at 0% premium."
    )

    brand_equity = df.groupby("brand").agg(
        products=("product_id", "size"),
        avg_price=("current_price", "mean"),
        discount_rate=("has_discount", lambda x: x.mean() * 100),
        avg_discount=("discount_pct", "mean"),
        sust_rate=("has_sustainability", lambda x: x.mean() * 100),
        breadth=("main_category", "nunique"),
        subcategories=("category_path", "nunique"),
        premium_pct=("price_premium_pct", "mean"),
    ).reset_index()
    brand_equity["share_pct"] = brand_equity["products"] / brand_equity["products"].sum() * 100

    # Composite "Brand Equity Score" — simple normalized index 0-100
    # High is better: high share, high breadth, low discount dependency, high sustainability
    def minmax(s):
        s = s.fillna(0)
        return (s - s.min()) / (s.max() - s.min() + 1e-9) * 100

    brand_equity["score"] = (
        0.30 * minmax(brand_equity["share_pct"])
        + 0.25 * minmax(brand_equity["breadth"])
        + 0.20 * (100 - minmax(brand_equity["discount_rate"]))  # less discounting = stronger
        + 0.15 * minmax(brand_equity["sust_rate"])
        + 0.10 * minmax(brand_equity["premium_pct"].clip(lower=0))
    ).round(1)
    brand_equity = brand_equity.sort_values("score", ascending=False)

    c1, c2, c3 = st.columns(3)
    c1.metric("Brands w/ score ≥ 70", (brand_equity["score"] >= 70).sum())
    c2.metric("Avg Brand Score", f"{brand_equity['score'].mean():.1f}")
    c3.metric("Top-10 score gap", f"{brand_equity['score'].head(10).std():.1f}",
              help="Std dev of scores across top-10 brands")

    st.divider()
    st.subheader("Brand Equity Scoreboard")
    st.caption(
        "Composite score weights: 30% assortment share · 25% category breadth · "
        "20% (inverse) discount dependency · 15% sustainability share · 10% price premium. "
        "Scores are min-max normalized within the filtered set."
    )
    min_products = st.slider("Min products per brand (filter noise)", 1, 50, 10)
    be_display = brand_equity[brand_equity["products"] >= min_products].reset_index(drop=True)

    fig = px.bar(be_display.head(20), x="score", y="brand", orientation="h",
                 color="share_pct", color_continuous_scale="Blues",
                 title=f"Top 20 Brand Equity Scores (min {min_products} products)",
                 labels={"score": "Brand Equity Score (0-100)", "brand": "", "share_pct": "Share %"},
                 template=PLOTLY_TEMPLATE)
    fig.update_layout(yaxis=dict(categoryorder="total ascending"))
    st.plotly_chart(fig, use_container_width=True)

    # Scatter: share vs pricing power, colored by discount dependency
    st.subheader("Strategic Quadrant — Assortment Share vs Price Premium")
    fig = px.scatter(
        be_display, x="share_pct", y="premium_pct",
        size="products", color="discount_rate", hover_name="brand",
        color_continuous_scale="RdYlGn_r",
        labels={"share_pct": "Assortment Share (%)", "premium_pct": "Price Premium vs Category (%)",
                "discount_rate": "% on Sale"},
        title="High share + high premium + low discount = strongest brand equity",
        template=PLOTLY_TEMPLATE,
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.add_vline(x=be_display["share_pct"].median(), line_dash="dash", line_color="gray", opacity=0.5)
    st.plotly_chart(fig, use_container_width=True)

    # Full table
    st.dataframe(
        be_display[["brand", "score", "products", "share_pct", "breadth",
                    "discount_rate", "sust_rate", "premium_pct", "avg_price"]],
        column_config={
            "brand": "Brand",
            "score": st.column_config.ProgressColumn("Equity Score", min_value=0, max_value=100, format="%.1f"),
            "products": st.column_config.NumberColumn("# Products", format="%d"),
            "share_pct": st.column_config.NumberColumn("Share %", format="%.2f%%"),
            "breadth": "Breadth",
            "discount_rate": st.column_config.NumberColumn("% on Sale", format="%.1f%%"),
            "sust_rate": st.column_config.NumberColumn("Sustainable %", format="%.1f%%"),
            "premium_pct": st.column_config.NumberColumn("Premium %", format="%.1f%%"),
            "avg_price": st.column_config.NumberColumn("Avg Price", format="%.0f"),
        },
        use_container_width=True, hide_index=True, height=500,
    )

    st.divider()
    st.info(
        "**Using this as a case study input:** treat brands with top equity scores "
        "(Patagonia, Carhartt WIP, Armedangels, Fjällräven) as benchmarks for Freshlabels' own "
        "house-brand positioning. Brands heavy on discounting (high % on Sale) signal weaker "
        "pricing power — a warning sign when mapping brand equity → LTV."
    )

# =============================================================================
# TAB 5: LTV vs CAC MODEL
# =============================================================================
with tab_ltv:
    st.markdown(
        "**Interactive LTV vs CAC simulator.** Compares a _brand-led_ customer "
        "(higher repeat, higher AOV, less discount-sensitive) against a "
        "_discount-led_ customer (lower repeat rate, lower AOV). Adjust assumptions in the sidebar."
    )
    st.caption(
        "**Abbreviations & formulas** — "
        "**LTV** (Customer Lifetime Value): total gross profit expected from a customer cohort over the chosen horizon. "
        "Calculated as Σ(orders × AOV × gross_margin%) across years, where the retained fraction "
        "compounds by the repeat rate each year. "
        "**CAC** (Customer Acquisition Cost): the total marketing spend divided by the number of new customers acquired. "
        "**AOV** (Average Order Value): average revenue per completed order, in CZK. "
        "**PNO** (Podíl Nákladů na Obratu — Czech): marketing cost as a % of total revenue; "
        "the Czech e-commerce standard equivalent of ROAS inverted. "
        "Lower PNO = more efficient marketing spend. "
        "**Gross Margin %**: revenue minus cost of goods, as a % of revenue. "
        "**Repeat Rate %**: probability that a customer places another order within 12 months. "
        "**LTV/CAC ≥ 3**: industry rule of thumb for healthy unit economics — "
        "a customer should generate at least 3× their acquisition cost in gross profit. "
        "**Non-Paid Traffic**: organic, direct, and SEO visitors who arrive without clicking a paid ad. "
        "Higher non-paid share reduces effective PNO because you pay less per visitor. "
        "**pp** (percentage points): absolute difference between two percentages "
        "(e.g. PNO rising from 10% to 12% = +2 pp, not +20%)."
    )

    st.subheader("Customer Segment Assumptions")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Brand-Led Customer**")
        brand_aov_mult = st.slider("AOV multiplier (brand)", 0.8, 1.5, 1.10, 0.05, key="brand_aov")
        brand_repeat_mult = st.slider("Repeat rate multiplier (brand)", 1.0, 3.0, 1.6, 0.1, key="brand_rep")
        brand_margin_mult = st.slider("Margin multiplier (brand)", 0.8, 1.3, 1.05, 0.05, key="brand_mar")
    with c2:
        st.markdown("**Discount-Led Customer**")
        disc_aov_mult = st.slider("AOV multiplier (discount)", 0.5, 1.2, 0.85, 0.05, key="disc_aov")
        disc_repeat_mult = st.slider("Repeat rate multiplier (discount)", 0.1, 1.0, 0.5, 0.05, key="disc_rep")
        disc_margin_mult = st.slider("Margin multiplier (discount)", 0.5, 1.0, 0.75, 0.05, key="disc_mar")

    horizon_years = st.slider("Time horizon (years)", 1, 5, 3)

    # LTV calculation
    def compute_ltv(aov_v, rr_pct, margin_pct, opy, horizon):
        """
        Simple cohort-style LTV.
        Orders in year 1 = 1 (first purchase) + repeat_rate * opy - 1 extra
        We treat repeat_rate as probability of buying again in a given year, then
        scale by orders_per_year once they're active.
        """
        rr = rr_pct / 100
        m = margin_pct / 100
        rows = []
        retained = 1.0  # fraction of cohort still active
        cum_value = 0.0
        for yr in range(1, horizon + 1):
            if yr == 1:
                orders = retained * 1.0  # first purchase by everyone
            else:
                orders = retained * opy
            gross_profit = orders * aov_v * m
            cum_value += gross_profit
            rows.append({
                "Year": yr, "Retained %": retained * 100,
                "Orders": orders, "Revenue": orders * aov_v,
                "Gross Profit": gross_profit, "Cumulative LTV": cum_value,
            })
            retained *= rr  # retention rolls forward
        return pd.DataFrame(rows)

    brand_df = compute_ltv(
        aov * brand_aov_mult, repeat_rate * brand_repeat_mult,
        gross_margin * brand_margin_mult, orders_per_year, horizon_years,
    )
    disc_df = compute_ltv(
        aov * disc_aov_mult, repeat_rate * disc_repeat_mult,
        gross_margin * disc_margin_mult, orders_per_year, horizon_years,
    )

    ltv_brand = brand_df["Cumulative LTV"].iloc[-1]
    ltv_disc = disc_df["Cumulative LTV"].iloc[-1]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"LTV — Brand Customer ({horizon_years}y)", f"{ltv_brand:,.0f} CZK")
    c2.metric(f"LTV — Discount Customer ({horizon_years}y)", f"{ltv_disc:,.0f} CZK")
    c3.metric("LTV Gap", f"{ltv_brand - ltv_disc:,.0f} CZK",
              delta=f"+{(ltv_brand/max(ltv_disc,1)-1)*100:.0f}%")
    c4.metric("Max allowable CAC (LTV/CAC=3)", f"{ltv_brand/3:,.0f} CZK",
              help="Golden rule: LTV/CAC ≥ 3 for healthy unit economics")

    st.divider()

    # Cumulative LTV curve
    comparison = pd.concat([
        brand_df.assign(Segment="Brand-Led"),
        disc_df.assign(Segment="Discount-Led"),
    ])
    fig = px.line(
        comparison, x="Year", y="Cumulative LTV", color="Segment", markers=True,
        title=f"Cumulative LTV over {horizon_years} years",
        labels={"Cumulative LTV": "Cumulative Gross Profit (CZK)"},
        color_discrete_sequence=[COLOR_PALETTE[0], COLOR_PALETTE[1]],
        template=PLOTLY_TEMPLATE,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Break-even CAC
    st.subheader("Break-even CAC Analysis")
    st.markdown(
        "The maximum CAC Freshlabels can afford depends on the payback horizon. "
        "Short-term-only acquisition (first purchase payback) caps CAC at first-order margin. "
        "A brand-led, retention-oriented view uses the multi-year LTV ceiling."
    )

    be_rows = []
    for seg_name, seg_df in [("Brand-Led", brand_df), ("Discount-Led", disc_df)]:
        be_rows.append({
            "Segment": seg_name,
            "1st-Purchase Break-even CAC": seg_df["Gross Profit"].iloc[0],
            f"{horizon_years}y LTV ceiling": seg_df["Cumulative LTV"].iloc[-1],
            "LTV/CAC=3 max CAC": seg_df["Cumulative LTV"].iloc[-1] / 3,
            "LTV/CAC=5 max CAC": seg_df["Cumulative LTV"].iloc[-1] / 5,
        })
    be_df = pd.DataFrame(be_rows)
    st.dataframe(
        be_df,
        column_config={
            col: st.column_config.NumberColumn(col, format="%.0f CZK")
            for col in be_df.columns if col != "Segment"
        },
        use_container_width=True, hide_index=True,
    )

    # Traffic mix sensitivity
    st.divider()
    st.subheader("Traffic-Mix Sensitivity: Brand Investment Scenario")
    st.markdown(
        "**Provocation from the case study:** What if brand investment shifts traffic from "
        "paid to non-paid but temporarily raises PNO by +2pp? Models impact on contribution margin."
    )

    scenarios = []
    for np_share in [30, 40, 50, 60, 70]:
        # Simplified: non-paid traffic costs nothing directly; paid share drives PNO
        # Baseline PNO applies at baseline paid_share
        baseline_paid = 100 - BASELINE["nonpaid_share"]
        effective_pno = pno * (100 - np_share) / baseline_paid
        # Scenario: brand investment = +2pp PNO when non-paid share grows
        if np_share > BASELINE["nonpaid_share"]:
            effective_pno += 2.0
        # Per-order contribution: GrossMargin - PNO
        contrib_per_order = aov * (gross_margin - effective_pno) / 100
        scenarios.append({
            "Non-Paid Traffic %": np_share,
            "Effective PNO %": round(effective_pno, 2),
            "Contribution / Order (CZK)": round(contrib_per_order, 0),
            "Delta vs Baseline": round(contrib_per_order - aov * (gross_margin - pno) / 100, 0),
        })
    scen_df = pd.DataFrame(scenarios)
    st.dataframe(scen_df, use_container_width=True, hide_index=True)

    fig = px.bar(
        scen_df, x="Non-Paid Traffic %", y="Contribution / Order (CZK)",
        color="Delta vs Baseline", color_continuous_scale="RdYlGn",
        title="Brand-led traffic shift lifts contribution margin",
        template=PLOTLY_TEMPLATE,
    )
    st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# TAB 6: PRICE PREMIUM
# =============================================================================
with tab_premium:
    st.markdown(
        "**Price premium = how much above (or below) the product-family average "
        "each brand charges.** Premium positioning is a direct observable proxy for brand "
        "pricing power (the Economic Moat)."
    )
    st.caption(
        "**How price premium is calculated**: for each product, the mean current price of all products "
        "in the same Product Family (top-level category) is computed. "
        "Price Premium % = (product_price − family_mean) / family_mean × 100. "
        "The brand-level figure is the average of this metric across all the brand's products. "
        "Positive = brand charges above the family average; negative = below. "
        "**Discount Dependency axis** in the scatter: % of the brand's SKUs currently on sale — "
        "ideal brands sit top-left (high premium, low discount reliance). "
        "**SKU** (Stock Keeping Unit): one individual product variant as it appears in the catalog."
    )

    min_n = st.slider("Min products per brand", 1, 50, 10, key="prem_min")
    valid_brands = df.groupby("brand").size()
    valid_brands = valid_brands[valid_brands >= min_n].index.tolist()
    dfp = df[df["brand"].isin(valid_brands)]

    # Brand-level premium
    brand_prem = dfp.groupby("brand").agg(
        products=("product_id", "size"),
        avg_price=("current_price", "mean"),
        premium_pct=("price_premium_pct", "mean"),
        discount_rate=("has_discount", lambda x: x.mean() * 100),
    ).reset_index().sort_values("premium_pct", ascending=False)

    # Waterfall-style bar
    fig = px.bar(
        brand_prem, x="premium_pct", y="brand", orientation="h",
        color="premium_pct", color_continuous_scale="RdBu", color_continuous_midpoint=0,
        title=f"Price Premium vs Family Average (brands with ≥ {min_n} products)",
        labels={"premium_pct": "Premium vs category avg (%)", "brand": ""},
        template=PLOTLY_TEMPLATE,
    )
    fig.update_layout(yaxis=dict(categoryorder="total ascending"))
    fig.add_vline(x=0, line_color="black", line_width=1)
    st.plotly_chart(fig, use_container_width=True)

    # Premium vs discount-dependency scatter
    st.subheader("Premium vs Discount Dependency")
    fig = px.scatter(
        brand_prem, x="discount_rate", y="premium_pct",
        size="products", hover_name="brand", color="premium_pct",
        color_continuous_scale="RdBu", color_continuous_midpoint=0,
        labels={"discount_rate": "% of SKUs on sale", "premium_pct": "Price premium (%)"},
        title="Ideal quadrant: top-left (high premium, low discount dependency)",
        template=PLOTLY_TEMPLATE,
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.add_vline(x=brand_prem["discount_rate"].median(), line_dash="dash", line_color="gray")
    st.plotly_chart(fig, use_container_width=True)

    # Family-level premium distribution
    st.subheader("Premium Distribution by Product Family")
    fig = px.box(
        dfp, x="main_category", y="price_premium_pct",
        title="How wide is the price range in each family? (wider = more room for premium)",
        labels={"main_category": "", "price_premium_pct": "Premium vs family avg (%)"},
        template=PLOTLY_TEMPLATE,
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_xaxes(tickangle=-30)
    st.plotly_chart(fig, use_container_width=True)

    # Table
    st.subheader("Brand Premium Table")
    st.dataframe(
        brand_prem,
        column_config={
            "brand": "Brand",
            "products": st.column_config.NumberColumn("# Products", format="%d"),
            "avg_price": st.column_config.NumberColumn("Avg Price (CZK)", format="%.0f"),
            "premium_pct": st.column_config.NumberColumn("Premium %", format="%+.1f%%"),
            "discount_rate": st.column_config.NumberColumn("% on Sale", format="%.1f%%"),
        },
        use_container_width=True, hide_index=True, height=400,
    )

# =============================================================================
# TAB 7: COMPETITOR PRICE PREMIUM (Queens.cz + future competitors)
# =============================================================================
with tab_comp_premium:
    render_competitor_premium()

# =============================================================================
# TAB 8: PRODUCT EXPLORER
# =============================================================================
with tab_explorer:
    st.markdown(
        "**Browse and search individual products** from the filtered catalog. "
        "Use the search box to filter by product name or brand, sort the table, "
        "and click *Product Detail* to inspect a single item including its image."
    )
    st.caption(
        "**Column guide** — "
        "**Price (CZK)**: current selling price. "
        "**Original**: original price before discount (shown only if different from current). "
        "**Discount**: (original − current) / original × 100. "
        "**Colors**: available colour options as scraped (pipe-separated). "
        "**Sustainability**: eco-labels attached to the product. "
        "**Promo**: promotional tags (e.g. *New arrival*, *Bestseller*)."
    )
    st.divider()
    c1, c2 = st.columns([3, 1])
    with c1:
        q = st.text_input("Search name or brand", "")
    with c2:
        sort_opt = st.selectbox("Sort by", [
            "Price (Low-High)", "Price (High-Low)", "Discount (Highest)", "Name (A-Z)",
        ])

    xdf = df.copy()
    if q:
        mask = xdf["name"].str.contains(q, case=False, na=False) | xdf["brand"].str.contains(q, case=False, na=False)
        xdf = xdf[mask]

    sort_map = {
        "Price (Low-High)": ("current_price", True),
        "Price (High-Low)": ("current_price", False),
        "Discount (Highest)": ("discount_pct", False),
        "Name (A-Z)": ("name", True),
    }
    sc, sa = sort_map[sort_opt]
    xdf = xdf.sort_values(sc, ascending=sa, na_position="last")

    st.caption(f"{len(xdf):,} products")

    table_cols = ["name", "brand", "category_path", "current_price", "original_price",
                  "discount_pct", "colors", "sustainability_labels", "promo_tags"]
    st.dataframe(
        xdf[table_cols].reset_index(drop=True),
        column_config={
            "name": st.column_config.TextColumn("Product", width="large"),
            "brand": "Brand",
            "category_path": "Category",
            "current_price": st.column_config.NumberColumn("Price (CZK)", format="%.0f"),
            "original_price": st.column_config.NumberColumn("Original", format="%.0f"),
            "discount_pct": st.column_config.NumberColumn("Discount", format="%.1f%%"),
            "colors": "Colors",
            "sustainability_labels": "Sustainability",
            "promo_tags": "Promo",
        },
        use_container_width=True, hide_index=True, height=500,
    )

    st.divider()
    st.subheader("Product Detail")
    names = xdf["name"] + " — " + xdf["brand"]
    if not names.empty:
        sel = st.selectbox("Select a product", names.values)
        if sel:
            idx = names[names == sel].index[0]
            row = xdf.loc[idx]
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown(f"### {row['name']}")
                st.markdown(f"**Brand:** {row['brand']}")
                st.markdown(f"**Category:** {row['category_path']}")
                st.markdown(f"**Price:** {row['current_price']:,.0f} CZK")
                if pd.notna(row["original_price"]) and row["original_price"] != row["current_price"]:
                    st.markdown(f"**Original:** ~~{row['original_price']:,.0f} CZK~~ ({row['discount_pct']:.1f}% off)")
                for fld in ["colors", "sizes_in_stock", "sustainability_labels", "promo_tags"]:
                    v = row.get(fld)
                    if pd.notna(v) and str(v):
                        st.markdown(f"**{fld.replace('_', ' ').title()}:** {v}")
                st.link_button("View on Freshlabels", row["url"])
            with c2:
                imgs = str(row.get("image_urls", ""))
                first = imgs.split("|")[0].strip() if imgs else ""
                if first:
                    st.image(first, use_container_width=True)
