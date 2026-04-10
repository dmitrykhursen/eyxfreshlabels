import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Freshlabels Asset Dashboard", layout="wide", page_icon="📈")

# ==========================================
# DATA LOADING & PREPROCESSING
# ==========================================
@st.cache_data
def load_data():
    try:
        posts_df = pd.read_csv('data/unfiltered/freshlabels_ig_posts.csv')
        collabs_df = pd.read_csv('data/unfiltered/freshlabels_collaborators.csv')
    except FileNotFoundError:
        st.error("Data files not found. Ensure 'freshlabels_ig_posts.csv' and 'freshlabels_collaborators.csv' are present.")
        return pd.DataFrame(), pd.DataFrame()

    # Preprocess Posts
    posts_df['Date'] = pd.to_datetime(posts_df['Date'], errors='coerce')
    posts_df['Likes'] = pd.to_numeric(posts_df['Likes'], errors='coerce').fillna(0)
    posts_df['Comments'] = pd.to_numeric(posts_df['Comments'], errors='coerce').fillna(0)
    posts_df['Total_Engagement'] = posts_df['Likes'] + posts_df['Comments']
    posts_df['Has_Collab'] = posts_df['Total_Collaborators'] > 0
    
    return posts_df, collabs_df

posts_df, collabs_df = load_data()

if posts_df.empty or collabs_df.empty:
    st.stop()

# ==========================================
# SIDEBAR: TIME FRAME FILTER
# ==========================================
st.sidebar.header("📅 Time Frame Filter")
st.sidebar.markdown("Filter all dashboard metrics by date.")

# Determine min and max dates in the dataset
min_date = posts_df['Date'].min()
max_date = posts_df['Date'].max()

time_options = ["1 Month", "3 Months", "6 Months", "1 Year", "All Time", "Custom Range"]
# Default to "1 Year" (index 3)
selected_time = st.sidebar.radio("Select Time Range", time_options, index=3)

# Calculate Start and End Dates based on selection
if selected_time == "1 Month":
    start_date = max_date - pd.DateOffset(months=1)
    end_date = max_date
elif selected_time == "3 Months":
    start_date = max_date - pd.DateOffset(months=3)
    end_date = max_date
elif selected_time == "6 Months":
    start_date = max_date - pd.DateOffset(months=6)
    end_date = max_date
elif selected_time == "1 Year":
    start_date = max_date - pd.DateOffset(years=1)
    end_date = max_date
elif selected_time == "All Time":
    start_date = min_date
    end_date = max_date
else: # Custom Range
    dates = st.sidebar.date_input("Select Date Range", [min_date.date(), max_date.date()], min_value=min_date.date(), max_value=max_date.date())
    if len(dates) == 2:
        start_date, end_date = pd.to_datetime(dates[0]), pd.to_datetime(dates[1])
    else:
        start_date, end_date = pd.to_datetime(dates[0]), pd.to_datetime(dates[0])

# --- DYNAMIC DATA FILTERING ---
# 1. Filter Posts
mask = (posts_df['Date'] >= start_date) & (posts_df['Date'] <= end_date)
filtered_posts = posts_df.loc[mask]

# 2. Filter Collaborators dynamically based on the filtered posts
valid_shortcodes = set(filtered_posts['Shortcode'])

def count_valid_appearances(shortcode_str):
    """Counts how many of a collaborator's posts fall within the selected date range."""
    if pd.isna(shortcode_str): return 0
    codes = [c.strip() for c in shortcode_str.split('|')]
    return sum(1 for c in codes if c in valid_shortcodes)

filtered_collabs = collabs_df.copy()
filtered_collabs['Filtered_Appearances'] = filtered_collabs['Post_Shortcodes'].apply(count_valid_appearances)
# Keep only collaborators who appeared in the selected time frame
filtered_collabs = filtered_collabs[filtered_collabs['Filtered_Appearances'] > 0]

# ==========================================
# HEADER & KPIs
# ==========================================
st.title("📈 Freshlabels: Advanced Marketing Case Study")
st.markdown(f"**Currently viewing data from:** `{start_date.strftime('%Y-%m-%d')}` to `{end_date.strftime('%Y-%m-%d')}`")

with st.expander("📚 View Dashboard Formulas & Definitions"):
    st.markdown("""
    **Formulas used in this dashboard:**
    * **Total Engagement:** $\\text{Likes} + \\text{Comments}$ 
    * **Content ROI (Return on Investment):** $\\frac{\\text{Total Engagement of a Format}}{\\text{Total Posts of that Format}}$ *(Measures which content type yields the most interaction per unit of effort).*
    * **Network Lift:** $\\frac{\\text{Avg. Collab Engagement} - \\text{Avg. Solo Engagement}}{\\text{Avg. Solo Engagement}} \\times 100$ *(Measures the percentage increase in engagement when partnering with another account).*
    """)

# Warn if no data in range
if filtered_posts.empty:
    st.warning("No posts found in the selected date range. Please select a wider time frame.")
    st.stop()

# ==========================================
# TABBED INTERFACE
# ==========================================
tab1, tab2, tab3 = st.tabs(["📊 Core Statistics & Timeline", "🎯 Content Format ROI", "🤝 Influencer & Network Effect"])

# ------------------------------------------
# TAB 1: CORE STATISTICS & TIMELINE
# ------------------------------------------
with tab1:
    st.header("1. Core Descriptive Statistics")
    st.markdown("A high-level overview of how the brand performs within the selected time frame.")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Posts in Range", f"{len(filtered_posts)}")
    col2.metric("Average Engagement", f"{filtered_posts['Total_Engagement'].mean():.0f}")
    col3.metric("Median Engagement", f"{filtered_posts['Total_Engagement'].median():.0f}")
    col4.metric("Max Engagement (Viral Peak)", f"{filtered_posts['Total_Engagement'].max():.0f}")

    st.markdown("---")
    st.header("2. Timeline: Engagement Over Time")
    st.markdown("This chart plots the exact trajectory of Likes and Comments over time. Use this to identify seasonal spikes (e.g., Christmas campaigns, summer sales) or dead zones.")
    
    timeline_df = filtered_posts.sort_values('Date')
    fig_time = px.line(timeline_df, x='Date', y=['Likes', 'Comments'], 
                       title="Historical Trajectory of Likes & Comments",
                       markers=True, color_discrete_sequence=['#FF4B4B', '#4B4BFF'])
    fig_time.update_layout(yaxis_title="Count", xaxis_title="Date of Post")
    st.plotly_chart(fig_time, use_container_width=True)

# ------------------------------------------
# TAB 2: CONTENT FORMAT ROI
# ------------------------------------------
with tab2:
    st.header("Content Strategy: What format works best?")
    st.markdown("Analyzing how Freshlabels allocates its content creation effort (Volume) versus the actual return it gets from the audience (ROI) within the chosen period.")
    
    format_stats = filtered_posts.groupby('Format_Type').agg(
        Post_Count=('Post_ID', 'count'),
        Avg_Engagement=('Total_Engagement', 'mean')
    ).reset_index()

    col2a, col2b = st.columns(2)
    with col2a:
        st.markdown("### Production Volume (Effort)")
        st.markdown("Shows what percentage of the total feed is made up of Carousels, Videos (Clips), or Single Images.")
        fig_vol = px.pie(format_stats, values='Post_Count', names='Format_Type', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig_vol, use_container_width=True)

    with col2b:
        st.markdown("### Content ROI (Reward)")
        st.markdown("Shows the **Average Engagement** each format receives. If a format has low volume but high ROI, the brand should produce more of it.")
        fig_roi = px.bar(format_stats, x='Format_Type', y='Avg_Engagement', text_auto='.0f', color='Format_Type')
        st.plotly_chart(fig_roi, use_container_width=True)

    st.markdown("---")
    st.header("Hit-Rate Analysis: Identifying 'Viral' Outliers")
    st.markdown("""
    This scatter plot shows every single post as a dot. The red dashed line is the **Average Engagement**. 
    Dots soaring high above the red line are your **Viral Outliers**. You can hover over them to see exactly which post broke the algorithm.
    """)
    
    fig_scatter = px.scatter(timeline_df, x='Date', y='Total_Engagement', color='Format_Type',
                             hover_data=['Shortcode', 'Likes', 'Comments'],
                             size_max=10, size=[5]*len(timeline_df),
                             title="Post-by-Post Performance vs. Average Baseline")
    
    # Add Average Line
    avg_eng = filtered_posts['Total_Engagement'].mean()
    fig_scatter.add_hline(y=avg_eng, line_dash="dash", line_color="red", annotation_text=f"Average: {avg_eng:.0f}")
    st.plotly_chart(fig_scatter, use_container_width=True)

# ------------------------------------------
# TAB 3: NETWORK & INFLUENCERS
# ------------------------------------------
with tab3:
    st.header("The Network Effect: Solo vs. Collaboration")
    st.markdown("Instagram rewards brands that interact with other accounts. This section proves whether paying or partnering with influencers/brands is actually working during this time frame.")
    
    collab_impact = filtered_posts.groupby('Has_Collab').agg(
        Avg_Engagement=('Total_Engagement', 'mean')
    ).reset_index()
    collab_impact['Strategy'] = collab_impact['Has_Collab'].map({True: 'Collabs/Tags', False: 'Solo Posts'})

    col3a, col3b = st.columns(2)
    with col3a:
        st.markdown("### Average Lift from Collaborations")
        st.markdown("Compares the raw average engagement of posts where Freshlabels tagged/co-authored with someone vs. posted entirely alone.")
        fig_lift = px.bar(collab_impact, x='Strategy', y='Avg_Engagement', text_auto='.0f', color='Strategy', color_discrete_sequence=['#50C878', '#FF6347'])
        st.plotly_chart(fig_lift, use_container_width=True)

    with col3b:
        st.markdown("### Influencer / Partner Roster Stats")
        st.markdown(f"A breakdown of the **{len(filtered_collabs)}** unique accounts Freshlabels associated with in this period.")
        
        total_partners = len(filtered_collabs)
        if total_partners > 0:
            verified_partners = len(filtered_collabs[filtered_collabs['Is_Verified'] == True])
            unverified_partners = total_partners - verified_partners
            
            roster_data = pd.DataFrame({
                'Status': ['Verified (Big Brands/Influencers)', 'Unverified (Micro/Niche)'],
                'Count': [verified_partners, unverified_partners]
            })
            fig_roster = px.pie(roster_data, values='Count', names='Status', hole=0.5, color_discrete_sequence=['#1DA1F2', '#AAB8C2'])
            st.plotly_chart(fig_roster, use_container_width=True)
        else:
            st.info("No collaborations found in this time frame.")

    st.markdown("---")
    st.header("Top Active Collaborators in Period")
    st.markdown("Who did Freshlabels rely on the most during the selected dates?")
    
    if not filtered_collabs.empty:
        top_collabs = filtered_collabs.sort_values(by='Filtered_Appearances', ascending=False).head(15)
        fig_top_collabs = px.bar(top_collabs, x='Filtered_Appearances', y='Username', 
                                 orientation='h', color='Is_Verified',
                                 hover_data=['Full_Name'],
                                 labels={'Is_Verified': 'Is Verified Account?', 'Filtered_Appearances': 'Appearances in Period'})
        fig_top_collabs.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_top_collabs, use_container_width=True)
    else:
        st.info("Adjust the time frame to see collaborator data.")