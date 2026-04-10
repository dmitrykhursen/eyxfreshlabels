import pandas as pd
import os

def analyze_competitor_sales(freshlabels_file: str, competitor_file: str, output_dir: str = "."):
    """
    Analyzes competitor sales for brands that are shared with Freshlabels.
    
    Args:
        freshlabels_file (str): Path to the Freshlabels CSV.
        competitor_file (str): Path to the scraped competitor CSV.
        output_dir (str): Directory to save the output CSVs.
    """
    print(f"Loading data from {freshlabels_file} and {competitor_file}...")
    
    # 1. Load the datasets
    df_fl = pd.read_csv(freshlabels_file)
    df_comp = pd.read_csv(competitor_file)
    
    # Normalize brand names to lowercase to ensure accurate matching
    df_fl['brand_norm'] = df_fl['brand'].astype(str).str.lower().str.strip()
    df_comp['brand_norm'] = df_comp['brand'].astype(str).str.lower().str.strip()
    
    # 2. Find shared brands
    fl_brands = set(df_fl['brand_norm'].unique())
    
    # 3. Filter competitor products to only include related (shared) brands
    df_related = df_comp[df_comp['brand_norm'].isin(fl_brands)].copy()
    
    # Drop the temporary normalized column before saving
    df_related = df_related.drop(columns=['brand_norm'])
    
    # 4. Save the related brands products to CSV
    os.makedirs(output_dir, exist_ok=True)
    related_products_path = os.path.join(output_dir, "related_brands_products.csv")
    df_related.to_csv(related_products_path, index=False)
    print(f"Saved {len(df_related)} related brand products to: {related_products_path}")
    
    # 5. Calculate statistics of sales per competitor
    # Ensure 'is_discounted' is boolean and 'discount_pct' is numeric
    df_related['is_discounted'] = df_related['is_discounted'].astype(bool)
    df_related['discount_pct'] = pd.to_numeric(df_related['discount_pct'], errors='coerce')
    
    stats = []
    
    # Group by competitor to calculate metrics
    for competitor, group in df_related.groupby('competitor'):
        total_products = len(group)
        sale_products = group['is_discounted'].sum()
        pct_on_sale = (sale_products / total_products) * 100 if total_products > 0 else 0
        
        # Calculate average discount only for items actually on sale
        avg_discount = group[group['is_discounted'] == True]['discount_pct'].mean()
        
        stats.append({
            'competitor': competitor,
            'related_brands_count': group['brand'].nunique(),
            'total_products': total_products,
            'products_on_sale': sale_products,
            'percent_on_sale': round(pct_on_sale, 2),
            'avg_discount_pct': round(avg_discount, 2) if pd.notna(avg_discount) else 0.0
        })
    
    df_stats = pd.DataFrame(stats)
    
    # 6. Save the statistics to CSV
    stats_path = os.path.join(output_dir, "competitor_sales_statistics.csv")
    df_stats.to_csv(stats_path, index=False)
    print(f"Saved sales statistics to: {stats_path}")
    
    print("\n--- Statistics Preview ---")
    print(df_stats.to_string(index=False))


if __name__ == "__main__":
    # Example usage:
    # Make sure you have your files named 'freshlabels.csv' and 'competitor.csv' in the same folder.
    
    # Uncomment the lines below to run on your actual files:
    freshlabels_file = "/home/dkhursen/Documents/webscrap-freshlabels/eyxfreshlabels/output/products.csv"
    competitor_file = "/home/dkhursen/Documents/webscrap-freshlabels/eyxfreshlabels/data/competitors/queens/all_products.csv"
    competitor_file2 = "/home/dkhursen/Documents/webscrap-freshlabels/eyxfreshlabels/data/competitors/nila/all_products.csv"
    competitor_file3 = "/home/dkhursen/Documents/webscrap-freshlabels/eyxfreshlabels/data/competitors/zalando/all_products.csv"

    # analyze_competitor_sales(freshlabels_file, competitor_file, "queens_related_data")
    # analyze_competitor_sales(freshlabels_file, competitor_file2, "nila_related_data")
    analyze_competitor_sales(freshlabels_file, competitor_file3, "zalando_related_data")
    # pass