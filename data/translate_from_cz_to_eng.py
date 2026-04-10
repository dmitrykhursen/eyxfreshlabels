import pandas as pd
from deep_translator import GoogleTranslator
import time

def translate_to_english(text):
    """Translates a single string from Czech to English."""
    if pd.isna(text) or not str(text).strip():
        return text
    try:
        return GoogleTranslator(source='cs', target='en').translate(str(text))
    except Exception as e:
        print(f"Translation failed for '{text}': {e}")
        return text

def translate_csv(input_csv: str, output_csv: str):
    print(f"Loading '{input_csv}'...")
    df = pd.read_csv(input_csv)
    
    print("Translating product names (Czech -> English)...")
    
    # Extract only unique product names to minimize translation API calls and speed up the process
    unique_names = df['product_name'].dropna().unique()
    translation_dict = {}
    
    total = len(unique_names)
    print(f"Found {total} unique product names to translate.")
    
    for i, name in enumerate(unique_names):
        translation_dict[name] = translate_to_english(name)
        
        # Print progress every 50 items and pause briefly to avoid rate-limiting
        if (i + 1) % 50 == 0 or (i + 1) == total:
            print(f"Translated {i + 1}/{total} unique items...")
            time.sleep(0.5) 
            
    # Map the translated English names back to the main dataframe
    print("Applying translations to the full dataset...")
    df['product_name'] = df['product_name'].map(translation_dict).fillna(df['product_name'])
    
    # Save the new CSV
    df.to_csv(output_csv, index=False)
    print(f"\nSuccess! Translated data saved to: '{output_csv}'")

if __name__ == "__main__":
    # Input and output file names
    INPUT_FILE = "competitors/zalando/all_products.csv"
    OUTPUT_FILE = "competitors/zalando/all_products_english.csv"
    
    translate_csv(INPUT_FILE, OUTPUT_FILE)