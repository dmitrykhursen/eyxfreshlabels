import pandas as pd
import argparse
import re
from datetime import datetime, timezone
import os

def parse_czk_price(price_str):
    """
    Extracts a float value from a Czech price string.
    Example: '891,00 Kč' -> 891.0
    """
    if pd.isna(price_str) or str(price_str).strip() == "":
        return None
    
    # Remove everything except digits and commas/periods
    cleaned = re.sub(r"[^\d,.]", "", str(price_str).replace("\xa0", "").replace(" ", ""))
    cleaned = cleaned.replace(",", ".")
    
    try:
        return float(cleaned)
    except ValueError:
        return None

def process_scraper_data(input1_path: str, input2_path: str, output_path: str):
    print(f"Loading data from {input1_path} and {input2_path}...")
    
    dfs = []
    for path in [input1_path, input2_path]:
        if os.path.exists(path):
            dfs.append(pd.read_csv(path, dtype=str))
        else:
            print(f"Warning: {path} not found. Skipping.")
            
    if not dfs:
        print("Error: No input files found to process.")
        return
        
    # Combine both CSVs
    raw_df = pd.concat(dfs, ignore_index=True)
    
    # Filter out empty rows or rows that are just 'outfit' pictures (missing brand and product)
    # Based on the Web Scraper sample: 'data' = brand, 'data2' = product name
    df_valid = raw_df.dropna(subset=['data', 'data2']).copy()
    df_valid = df_valid[(df_valid['data'].str.strip() != "") & (df_valid['data2'].str.strip() != "")]
    
    # Current timestamp for scraped_at
    scraped_at = datetime.now(timezone.utc).isoformat()
    
    processed_rows = []
    
    for _, row in df_valid.iterrows():
        brand = str(row['data']).strip()
        product_name = str(row['data2']).strip()
        url = str(row['web_scraper_start_url']).strip()
        
        # In Zalando Web Scraper data:
        # data3 is usually the current/discounted price
        # data4 is usually the original price (if discounted)
        # data5 is usually the discount percentage
        
        val3 = parse_czk_price(row.get('data3'))
        val4 = parse_czk_price(row.get('data4'))
        
        original_price = None
        discounted_price = None
        
        # Determine pricing logic
        if val3 is not None and val4 is not None:
            # Both present: max is original, min is discounted
            original_price = max(val3, val4)
            discounted_price = min(val3, val4)
        elif val3 is not None:
            # Only one price present -> not discounted
            original_price = val3
        elif val4 is not None:
            # Only one price present -> not discounted
            original_price = val4
            
        is_discounted = discounted_price is not None and discounted_price < original_price
        
        discount_pct = None
        if is_discounted and original_price > 0:
            discount_pct = round(((original_price - discounted_price) / original_price) * 100, 1)
            
        processed_rows.append({
            "product_name": product_name,
            "brand": brand,
            "scraped_brand": brand,
            "price_czk": original_price,
            "discounted_price_czk": discounted_price if is_discounted else None,
            "is_discounted": is_discounted,
            "discount_pct": discount_pct,
            "url": url,
            "competitor": "zalando",
            "scraped_at": scraped_at
        })

    # Create the final DataFrame
    final_df = pd.DataFrame(processed_rows)
    
    # Save the output
    final_df.to_csv(output_path, index=False)
    print(f"Successfully processed {len(final_df)} products.")
    print(f"Saved to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert raw Web Scraper CSVs to Freshlabels standard schema.")
    
    parser.add_argument("-i1", "--input1", required=True, help="Path to the first input CSV file")
    parser.add_argument("-i2", "--input2", required=True, help="Path to the second input CSV file")
    parser.add_argument("-o", "--output", default="top10_related_to_FL_products.csv", 
                        help="Path to save the output CSV (default: top10_related_to_FL_products.csv)")
    
    args = parser.parse_args()
    
    process_scraper_data(args.input1, args.input2, args.output)

# python convert_chrome_web_scraper_data.py -i1 competitors/zalando/zalando-cz-2026-04-10.csv -i2 competitors/zalando/zalando-cz-2026-04-10-2.csv -o competitors/zalando/top10_related_to_FL_products.csv