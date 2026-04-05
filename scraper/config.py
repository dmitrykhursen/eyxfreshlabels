"""
All tunable settings for the Freshlabels scraper.
Edit this file to change which categories to scrape, output format, delays, etc.
"""

BASE_URL = "https://www.freshlabels.cz"

# Categories to scrape. Each entry needs a unique 'name' and a 'url'.
CATEGORIES = [
    {"name": "clothes_women", "url": f"{BASE_URL}/en/clothes/women/"},
    {"name": "clothes_men",   "url": f"{BASE_URL}/en/clothes/men/"},
    {"name": "shoes",         "url": f"{BASE_URL}/en/shoes/"},
    {"name": "luggage",       "url": f"{BASE_URL}/en/luggage/"},
    {"name": "accessories",   "url": f"{BASE_URL}/en/accessories/"},
]

# Output paths
OUTPUT_DIR  = "output"
STATE_DIR   = "state"
OUTPUT_CSV  = f"{OUTPUT_DIR}/products.csv"
OUTPUT_JSON = f"{OUTPUT_DIR}/products.json"
STATE_FILE  = f"{STATE_DIR}/scraped_urls.txt"

# "csv", "json", or "both"
OUTPUT_FORMAT = "both"

# Set to True to also fetch individual product detail pages (sizes, all images).
# False = faster, uses only listing-page data (~36 fields still populated).
SCRAPE_DETAIL_PAGES = True

# Polite scraping — seconds between HTTP requests (+ random jitter)
DELAY_BETWEEN_REQUESTS = 2.0
DELAY_JITTER           = 0.5   # actual delay = DELAY ± uniform(0, JITTER)

MAX_RETRIES    = 3
RETRY_BACKOFF  = 5  # seconds before first retry; doubles each attempt

# Browser-like user-agent. The site blocks known bot agents.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 30  # seconds
