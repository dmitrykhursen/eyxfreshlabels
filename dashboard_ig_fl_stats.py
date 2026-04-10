import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

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
    
    # Preprocess Collaborators
    collabs_df['Total_Appearances'] = pd.to_numeric(collabs_df['Total_Appearances'], errors='coerce').fillna(0)

    return posts_df, collabs_df

posts_df, collabs_df = load_data()

if posts_df.empty or collabs_df.empty:
    st.stop()

# ==========================================
# HEADER & MATHEMATICAL DEFINITIONS
# ==========================================
st.title("📈 Freshlabels: Advanced Marketing Case Study")
st.markdown("""
This dashboard evaluates Freshlabels' organic Instagram strategy. By analyzing post formats, timelines, and influencer networks, we can deduce what drives the most brand value.
""")

with st.expander("📚 View Dashboard Formulas & Definitions"):
    st.markdown("""
    **Formulas used in this dashboard:**
    * **Total Engagement:** $\\text{Likes} + \\text{Comments}$ 
    * **Content ROI (Return on Investment):** $\\frac{\\text{Total Engagement of a Format}}{\\text{Total Posts of that Format}}$ *(Measures which content type yields the most interaction per unit of effort).*
    * **Network Lift:** $\\frac{\\text{Avg. Collab Engagement} - \\text{Avg. Solo Engagement}}{\\text{Avg. Solo Engagement}} \\times 100$ *(Measures the percentage increase in engagement when partnering with another account).*
    """)

# ==========================================
# TABBED INTERFACE
# ==========================================
tab1, tab2, tab3 = st.tabs(["📊 Core Statistics & Timeline", "🎯 Content Format ROI", "🤝 Influencer & Network Effect"])

# ------------------------------------------
# TAB 1: CORE STATISTICS & TIMELINE
# ------------------------------------------
with tab1:
    st.header("1. Core Descriptive Statistics")
    st.markdown("A high-level overview of how the brand performs on an average day, identifying the absolute floor (Min) and ceiling (Max) of their reach.")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Average Engagement", f"{posts_df['Total_Engagement'].mean():.0f}")
    col2.metric("Median Engagement", f"{posts_df['Total_Engagement'].median():.0f}")
    col3.metric("Max Engagement (Viral Peak)", f"{posts_df['Total_Engagement'].max():.0f}")
    col4.metric("Min Engagement (Floor)", f"{posts_df['Total_Engagement'].min():.0f}")

    st.markdown("---")
    st.header("2. Timeline: Engagement Over Time")
    st.markdown("This chart plots the exact trajectory of Likes and Comments over time. Use this to identify seasonal spikes (e.g., Christmas campaigns, summer sales) or dead zones.")
    
    timeline_df = posts_df.dropna(subset=['Date']).sort_values('Date')
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
    st.markdown("Analyzing how Freshlabels allocates its content creation effort (Volume) versus the actual return it gets from the audience (ROI).")
    
    format_stats = posts_df.groupby('Format_Type').agg(
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
    *(Replacing the Box Plot)*: This scatter plot shows every single post as a dot. The red dashed line is the **Average Engagement**. 
    Dots soaring high above the red line are your **Viral Outliers**. You can hover over them to see exactly which post broke the algorithm.
    """)
    
    fig_scatter = px.scatter(timeline_df, x='Date', y='Total_Engagement', color='Format_Type',
                             hover_data=['Shortcode', 'Likes', 'Comments'],
                             size_max=10, size=[5]*len(timeline_df),
                             title="Post-by-Post Performance vs. Average Baseline")
    
    # Add Average Line
    avg_eng = posts_df['Total_Engagement'].mean()
    fig_scatter.add_hline(y=avg_eng, line_dash="dash", line_color="red", annotation_text=f"Average: {avg_eng:.0f}")
    st.plotly_chart(fig_scatter, use_container_width=True)

# ------------------------------------------
# TAB 3: NETWORK & INFLUENCERS
# ------------------------------------------
with tab3:
    st.header("The Network Effect: Solo vs. Collaboration")
    st.markdown("Instagram rewards brands that interact with other accounts. This section proves whether paying or partnering with influencers/brands is actually working for Freshlabels.")
    
    collab_impact = posts_df.groupby('Has_Collab').agg(
        Avg_Engagement=('Total_Engagement', 'mean'),
        Median_Engagement=('Total_Engagement', 'median')
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
        st.markdown("A breakdown of the accounts Freshlabels associates with.")
        
        total_partners = len(collabs_df)
        verified_partners = len(collabs_df[collabs_df['Is_Verified'] == True])
        unverified_partners = total_partners - verified_partners
        
        roster_data = pd.DataFrame({
            'Status': ['Verified (Big Brands/Influencers)', 'Unverified (Micro/Niche)'],
            'Count': [verified_partners, unverified_partners]
        })
        fig_roster = px.pie(roster_data, values='Count', names='Status', hole=0.5, color_discrete_sequence=['#1DA1F2', '#AAB8C2'])
        st.plotly_chart(fig_roster, use_container_width=True)

    st.markdown("---")
    st.header("Top 15 Most Frequent Collaborators")
    st.markdown("Who does Freshlabels rely on the most? This chart sorts partners by how many times they appeared on the feed.")
    
    top_collabs = collabs_df.sort_values(by='Total_Appearances', ascending=False).head(15)
    fig_top_collabs = px.bar(top_collabs, x='Total_Appearances', y='Username', 
                             orientation='h', color='Is_Verified',
                             hover_data=['Full_Name', 'Coauthored_Posts', 'Tagged_Posts'],
                             labels={'Is_Verified': 'Is Verified Account?'})
    fig_top_collabs.update_layout(yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig_top_collabs, use_container_width=True)
    
    st.info("💡 **Strategic Takeaway:** If the top collaborators are heavily 'Unverified', it signifies Freshlabels relies on niche, community-driven micro-influencers rather than massive, expensive celebrities.")