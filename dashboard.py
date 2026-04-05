"""
Freshlabels.cz Product Analytics Dashboard
Run with:  streamlit run dashboard.py
"""

import glob
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Freshlabels Analytics",
    page_icon=":shopping_bags:",
    layout="wide",
    initial_sidebar_state="expanded",
)

COLOR_PALETTE = px.colors.qualitative.Set2
PLOTLY_TEMPLATE = "plotly_white"


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

    # Deduplicate — keep most recently scraped version of each product
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
    df = (
        df.sort_values("scraped_at", ascending=False)
        .drop_duplicates(subset="product_id", keep="first")
        .reset_index(drop=True)
    )

    # Derived columns
    df["has_discount"] = df["discount_pct"].fillna(0) > 0
    df["has_sustainability"] = df["sustainability_labels"].fillna("").str.len() > 0
    df["sub_category"] = (
        df["category_path"]
        .fillna("")
        .apply(lambda x: x.split(" > ")[-1] if x else "Unknown")
    )
    return df


def explode_pipe_field(series: pd.Series) -> pd.Series:
    """Split pipe-delimited values into individual rows, cleaned."""
    return (
        series.dropna()
        .str.split("|")
        .explode()
        .str.strip()
        .pipe(lambda s: s[s != ""])
    )


def clean_sizes(series: pd.Series) -> pd.Series:
    """Explode sizes and remove 'last chance to buy' artifacts."""
    exploded = explode_pipe_field(series)
    return exploded.str.replace(r"\s*last chance to buy.*", "", regex=True).str.strip()


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df_all = load_data()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")

categories = sorted(df_all["category"].unique())
sel_categories = st.sidebar.multiselect("Category", categories, default=categories)

brands = sorted(df_all["brand"].dropna().unique())
sel_brands = st.sidebar.multiselect("Brand", brands, default=brands)

price_min = float(df_all["current_price"].min())
price_max = float(df_all["current_price"].max())
sel_price = st.sidebar.slider(
    "Price range (CZK)",
    min_value=price_min,
    max_value=price_max,
    value=(price_min, price_max),
    step=10.0,
)

only_discounted = st.sidebar.checkbox("Only discounted products")
only_sustainable = st.sidebar.checkbox("Only sustainable products")

# Apply filters
df = df_all.copy()
df = df[df["category"].isin(sel_categories)]
df = df[df["brand"].isin(sel_brands)]
df = df[df["current_price"].between(sel_price[0], sel_price[1])]
if only_discounted:
    df = df[df["has_discount"]]
if only_sustainable:
    df = df[df["has_sustainability"]]

st.sidebar.divider()
st.sidebar.caption(f"Showing **{len(df)}** of {len(df_all)} products")

# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------
st.title("Freshlabels.cz Product Analytics")

if df.empty:
    st.warning("No products match current filters. Adjust the sidebar.")
    st.stop()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_overview, tab_brands, tab_pricing, tab_explorer = st.tabs(
    ["Overview", "Brands", "Pricing & Discounts", "Product Explorer"]
)

# ===== TAB 1: OVERVIEW =====
with tab_overview:
    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Products", f"{len(df):,}")
    avg_price = df["current_price"].mean()
    med_price = df["current_price"].median()
    c2.metric("Avg Price", f"{avg_price:,.0f} CZK", delta=f"Median: {med_price:,.0f}")
    pct_sale = df["has_discount"].mean() * 100
    c3.metric("On Sale", f"{pct_sale:.1f}%", delta=f"{df['has_discount'].sum()} products")
    c4.metric("Unique Brands", df["brand"].nunique())

    st.divider()

    # Category distribution + subcategory breakdown
    col_left, col_right = st.columns(2)
    with col_left:
        cat_counts = df["category"].value_counts().reset_index()
        cat_counts.columns = ["Category", "Count"]
        fig = px.pie(
            cat_counts, names="Category", values="Count",
            title="Products by Category",
            color_discrete_sequence=COLOR_PALETTE,
            template=PLOTLY_TEMPLATE,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        sub_counts = (
            df["category_path"].value_counts().head(15).reset_index()
        )
        sub_counts.columns = ["Subcategory", "Count"]
        fig = px.bar(
            sub_counts, x="Count", y="Subcategory", orientation="h",
            title="Top Subcategories",
            color_discrete_sequence=COLOR_PALETTE,
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig, use_container_width=True)

    # Price distribution
    fig = px.histogram(
        df, x="current_price", color="category", nbins=25,
        title="Price Distribution by Category",
        labels={"current_price": "Price (CZK)", "category": "Category"},
        color_discrete_sequence=COLOR_PALETTE,
        template=PLOTLY_TEMPLATE,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Promo tags
    promo_data = explode_pipe_field(df["promo_tags"])
    if not promo_data.empty:
        promo_counts = promo_data.value_counts().head(10).reset_index()
        promo_counts.columns = ["Tag", "Count"]
        fig = px.bar(
            promo_counts, x="Count", y="Tag", orientation="h",
            title="Most Common Promo Tags",
            color_discrete_sequence=COLOR_PALETTE,
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig, use_container_width=True)

# ===== TAB 2: BRANDS =====
with tab_brands:
    # Products per brand
    brand_counts = df.groupby(["brand", "category"]).size().reset_index(name="Count")
    fig = px.bar(
        brand_counts, x="brand", y="Count", color="category",
        title="Products per Brand",
        labels={"brand": "Brand"},
        color_discrete_sequence=COLOR_PALETTE,
        template=PLOTLY_TEMPLATE,
    )
    fig.update_layout(xaxis=dict(categoryorder="total descending"))
    st.plotly_chart(fig, use_container_width=True)

    # Brand price box plot
    fig = px.box(
        df, x="brand", y="current_price",
        title="Price Distribution by Brand",
        labels={"brand": "Brand", "current_price": "Price (CZK)"},
        color_discrete_sequence=COLOR_PALETTE,
        template=PLOTLY_TEMPLATE,
    )
    # Sort by median price descending
    brand_medians = df.groupby("brand")["current_price"].median().sort_values(ascending=False)
    fig.update_layout(xaxis=dict(categoryorder="array", categoryarray=brand_medians.index.tolist()))
    st.plotly_chart(fig, use_container_width=True)

    col_l, col_r = st.columns(2)

    with col_l:
        # Brand avg discount
        brand_disc = (
            df[df["has_discount"]]
            .groupby("brand")["discount_pct"]
            .mean()
            .sort_values(ascending=False)
            .head(15)
            .reset_index()
        )
        brand_disc.columns = ["Brand", "Avg Discount (%)"]
        if not brand_disc.empty:
            fig = px.bar(
                brand_disc, x="Avg Discount (%)", y="Brand", orientation="h",
                title="Average Discount by Brand (discounted items only)",
                color_discrete_sequence=COLOR_PALETTE,
                template=PLOTLY_TEMPLATE,
            )
            fig.update_layout(yaxis=dict(categoryorder="total ascending"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No discounted products in current filter.")

    with col_r:
        # Brand sustainability rate
        brand_sust = (
            df.groupby("brand")["has_sustainability"]
            .mean()
            .mul(100)
            .sort_values(ascending=False)
            .head(15)
            .reset_index()
        )
        brand_sust.columns = ["Brand", "Sustainable (%)"]
        fig = px.bar(
            brand_sust, x="Sustainable (%)", y="Brand", orientation="h",
            title="Sustainability Rate by Brand",
            color_discrete_sequence=[COLOR_PALETTE[2]],
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig, use_container_width=True)

    # Treemap
    tree_data = (
        df.groupby(["brand", "category_path"])
        .agg(count=("product_id", "size"), avg_price=("current_price", "mean"))
        .reset_index()
    )
    if not tree_data.empty:
        fig = px.treemap(
            tree_data,
            path=["brand", "category_path"],
            values="count",
            color="avg_price",
            color_continuous_scale="Blues",
            title="Brand-Category Map (size = product count, color = avg price)",
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(margin=dict(t=50, l=10, r=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

# ===== TAB 3: PRICING & DISCOUNTS =====
with tab_pricing:
    discounted = df[df["has_discount"]]

    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    avg_disc = discounted["discount_pct"].mean() if not discounted.empty else 0
    max_disc = discounted["discount_pct"].max() if not discounted.empty else 0
    c1.metric("Avg Discount", f"{avg_disc:.1f}%")
    c2.metric("Max Discount", f"{max_disc:.1f}%")
    c3.metric("Median Price", f"{df['current_price'].median():,.0f} CZK")
    c4.metric("Price Range", f"{df['current_price'].min():,.0f} - {df['current_price'].max():,.0f} CZK")

    st.divider()

    # Current vs Original price scatter
    scatter_df = df.dropna(subset=["current_price", "original_price"])
    if not scatter_df.empty:
        fig = px.scatter(
            scatter_df, x="original_price", y="current_price",
            color="discount_pct",
            color_continuous_scale="RdYlGn_r",
            hover_data=["name", "brand", "discount_pct"],
            title="Current vs Original Price",
            labels={
                "original_price": "Original Price (CZK)",
                "current_price": "Current Price (CZK)",
                "discount_pct": "Discount %",
            },
            template=PLOTLY_TEMPLATE,
        )
        # Reference line y = x (no discount)
        max_val = max(scatter_df["original_price"].max(), scatter_df["current_price"].max())
        fig.add_trace(
            go.Scatter(
                x=[0, max_val], y=[0, max_val],
                mode="lines", line=dict(dash="dash", color="gray"),
                name="No discount (y=x)",
            )
        )
        st.plotly_chart(fig, use_container_width=True)

    col_l, col_r = st.columns(2)

    with col_l:
        # Discount distribution
        if not discounted.empty:
            fig = px.histogram(
                discounted, x="discount_pct", nbins=20,
                title="Discount Distribution (discounted items)",
                labels={"discount_pct": "Discount (%)"},
                color_discrete_sequence=[COLOR_PALETTE[1]],
                template=PLOTLY_TEMPLATE,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No discounted products in current filter.")

    with col_r:
        # Discount by subcategory
        if not discounted.empty:
            top_subs = discounted["sub_category"].value_counts().head(10).index
            fig = px.box(
                discounted[discounted["sub_category"].isin(top_subs)],
                x="sub_category", y="discount_pct",
                title="Discount Range by Subcategory",
                labels={"sub_category": "Subcategory", "discount_pct": "Discount (%)"},
                color_discrete_sequence=COLOR_PALETTE,
                template=PLOTLY_TEMPLATE,
            )
            st.plotly_chart(fig, use_container_width=True)

    # Top expensive / cheapest tables
    st.subheader("Price Extremes")
    col_exp, col_chp = st.columns(2)

    display_cols = ["name", "brand", "category_path", "current_price", "original_price", "discount_pct"]

    with col_exp:
        st.markdown("**Top 10 Most Expensive**")
        top_exp = df.nlargest(10, "current_price")[display_cols].reset_index(drop=True)
        st.dataframe(
            top_exp,
            column_config={
                "current_price": st.column_config.NumberColumn("Price (CZK)", format="%.0f"),
                "original_price": st.column_config.NumberColumn("Original (CZK)", format="%.0f"),
                "discount_pct": st.column_config.NumberColumn("Discount %", format="%.1f%%"),
            },
            use_container_width=True,
            hide_index=True,
        )

    with col_chp:
        st.markdown("**Top 10 Cheapest**")
        top_chp = df.nsmallest(10, "current_price")[display_cols].reset_index(drop=True)
        st.dataframe(
            top_chp,
            column_config={
                "current_price": st.column_config.NumberColumn("Price (CZK)", format="%.0f"),
                "original_price": st.column_config.NumberColumn("Original (CZK)", format="%.0f"),
                "discount_pct": st.column_config.NumberColumn("Discount %", format="%.1f%%"),
            },
            use_container_width=True,
            hide_index=True,
        )

    # Sustainability premium
    st.divider()
    sust_df = df[["current_price", "has_sustainability"]].copy()
    sust_df["Sustainability"] = sust_df["has_sustainability"].map(
        {True: "Sustainable", False: "Not Sustainable"}
    )
    fig = px.box(
        sust_df, x="Sustainability", y="current_price",
        title="Do Sustainable Products Cost More?",
        labels={"current_price": "Price (CZK)"},
        color="Sustainability",
        color_discrete_sequence=[COLOR_PALETTE[2], COLOR_PALETTE[0]],
        template=PLOTLY_TEMPLATE,
    )
    st.plotly_chart(fig, use_container_width=True)


# ===== TAB 4: PRODUCT EXPLORER =====
with tab_explorer:
    # Search and sort
    col_search, col_sort = st.columns([3, 1])
    with col_search:
        search_query = st.text_input("Search products by name or brand", "")
    with col_sort:
        sort_option = st.selectbox("Sort by", [
            "Price (Low to High)",
            "Price (High to Low)",
            "Discount (Highest)",
            "Name (A-Z)",
        ])

    explore_df = df.copy()

    # Apply search
    if search_query:
        mask = (
            explore_df["name"].str.contains(search_query, case=False, na=False)
            | explore_df["brand"].str.contains(search_query, case=False, na=False)
        )
        explore_df = explore_df[mask]

    # Apply sort
    sort_map = {
        "Price (Low to High)": ("current_price", True),
        "Price (High to Low)": ("current_price", False),
        "Discount (Highest)": ("discount_pct", False),
        "Name (A-Z)": ("name", True),
    }
    sort_col, sort_asc = sort_map[sort_option]
    explore_df = explore_df.sort_values(sort_col, ascending=sort_asc, na_position="last")

    st.caption(f"{len(explore_df)} products")

    # Product table
    table_cols = [
        "name", "brand", "category_path", "current_price", "original_price",
        "discount_pct", "colors", "sustainability_labels", "promo_tags",
    ]
    st.dataframe(
        explore_df[table_cols].reset_index(drop=True),
        column_config={
            "name": st.column_config.TextColumn("Product", width="large"),
            "brand": "Brand",
            "category_path": "Category",
            "current_price": st.column_config.NumberColumn("Price (CZK)", format="%.0f"),
            "original_price": st.column_config.NumberColumn("Original (CZK)", format="%.0f"),
            "discount_pct": st.column_config.NumberColumn("Discount %", format="%.1f%%"),
            "colors": "Colors",
            "sustainability_labels": "Sustainability",
            "promo_tags": "Promo Tags",
        },
        use_container_width=True,
        hide_index=True,
        height=500,
    )

    # Sustainability labels deep-dive
    st.divider()
    sust_labels = explode_pipe_field(df["sustainability_labels"])
    if not sust_labels.empty:
        sust_counts = sust_labels.value_counts().reset_index()
        sust_counts.columns = ["Label", "Count"]
        fig = px.bar(
            sust_counts, x="Count", y="Label", orientation="h",
            title="Sustainability Labels Breakdown",
            color_discrete_sequence=[COLOR_PALETTE[2]],
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No sustainability labels in current data.")

    # Product detail viewer
    st.divider()
    st.subheader("Product Detail")
    product_names = explore_df["name"] + " — " + explore_df["brand"]
    if not product_names.empty:
        selected = st.selectbox("Select a product", product_names.values)
        if selected:
            idx = product_names[product_names == selected].index[0]
            row = explore_df.loc[idx]

            col_info, col_img = st.columns([2, 1])
            with col_info:
                st.markdown(f"### {row['name']}")
                st.markdown(f"**Brand:** {row['brand']}")
                st.markdown(f"**Category:** {row['category_path']}")
                st.markdown(f"**Price:** {row['current_price']:,.0f} CZK")
                if pd.notna(row["original_price"]) and row["original_price"] != row["current_price"]:
                    st.markdown(f"**Original Price:** ~~{row['original_price']:,.0f} CZK~~ ({row['discount_pct']:.1f}% off)")
                if pd.notna(row.get("colors")) and row["colors"]:
                    st.markdown(f"**Colors:** {row['colors']}")
                if pd.notna(row.get("sizes_in_stock")) and row["sizes_in_stock"]:
                    st.markdown(f"**Sizes:** {row['sizes_in_stock']}")
                if pd.notna(row.get("sustainability_labels")) and row["sustainability_labels"]:
                    st.markdown(f"**Sustainability:** {row['sustainability_labels']}")
                if pd.notna(row.get("promo_tags")) and row["promo_tags"]:
                    st.markdown(f"**Promo:** {row['promo_tags']}")
                st.link_button("View on Freshlabels", row["url"])

            with col_img:
                img_urls = str(row.get("image_urls", ""))
                first_img = img_urls.split("|")[0].strip() if img_urls else ""
                if first_img:
                    st.image(first_img, use_container_width=True)
