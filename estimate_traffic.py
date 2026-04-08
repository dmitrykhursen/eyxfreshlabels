"""
Estimate monthly visitors to freshlabels.cz using free public data sources.

Sources used:
1. Similarweb public data endpoint (free, no key) — main traffic estimate
2. Google Trends via pytrends — relative search interest for cross-check
3. Derived signals: bounce rate, avg visit duration, traffic country split

Usage:
    pip install requests pytrends
    python estimate_traffic.py
    python estimate_traffic.py --domain freshlabels.cz
    python estimate_traffic.py --compare zoot.cz,aboutyou.cz
"""

import argparse
import json
import sys
from datetime import datetime

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.similarweb.com/",
}


def fetch_similarweb(domain: str) -> dict | None:
    """
    Hit Similarweb's public JSON endpoint used by their free website-analysis
    page. No API key required. Returns None if the domain isn't tracked.
    """
    url = f"https://data.similarweb.com/api/v1/data?domain={domain}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"  Similarweb returned HTTP {resp.status_code}")
            return None
        data = resp.json()
        if "Error" in data or "Meta" not in data:
            print(f"  Similarweb: domain not tracked ({data.get('Error', 'no data')})")
            return None
        return data
    except (requests.RequestException, json.JSONDecodeError) as exc:
        print(f"  Similarweb fetch failed: {exc}")
        return None


def summarize_similarweb(data: dict) -> dict:
    """Extract the headline numbers from the Similarweb payload."""
    engagements = data.get("Engagments", {})  # (sic — typo in Similarweb API)
    est_visits = float(engagements.get("Visits", 0)) if engagements.get("Visits") else 0
    bounce = float(engagements.get("BounceRate", 0)) if engagements.get("BounceRate") else 0
    pages_per_visit = float(engagements.get("PagePerVisit", 0)) if engagements.get("PagePerVisit") else 0
    avg_duration = engagements.get("TimeOnSite", "0")  # seconds string

    # Country breakdown
    top_countries = data.get("TopCountryShares", [])[:5]
    # Traffic sources
    sources = data.get("TrafficSources", {})

    # Monthly history (last 3 months)
    visits_hist = data.get("EstimatedMonthlyVisits", {})

    return {
        "estimated_visits": int(est_visits),
        "bounce_rate_pct": round(bounce * 100, 1),
        "pages_per_visit": round(pages_per_visit, 2),
        "avg_visit_seconds": int(float(avg_duration)),
        "top_countries": top_countries,
        "traffic_sources": sources,
        "monthly_history": visits_hist,
        "global_rank": data.get("GlobalRank", {}).get("Rank"),
        "country_rank": data.get("CountryRank", {}).get("Rank"),
        "category": data.get("Category"),
    }


def fetch_google_trends(keyword: str, geo: str = "CZ") -> dict | None:
    """
    Pull 12-month trend data for a keyword via pytrends (unofficial, free).
    Returns average interest score (0-100) and whether trend is rising.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("  pytrends not installed — skipping Google Trends")
        print("  (install with: pip install pytrends)")
        return None

    try:
        pytrends = TrendReq(hl="en-US", tz=60)
        pytrends.build_payload([keyword], timeframe="today 12-m", geo=geo)
        df = pytrends.interest_over_time()
        if df.empty:
            return None
        avg = float(df[keyword].mean())
        recent_3mo = float(df[keyword].tail(12).mean())
        older_3mo = float(df[keyword].head(12).mean())
        trend_direction = "rising" if recent_3mo > older_3mo * 1.05 else (
            "falling" if recent_3mo < older_3mo * 0.95 else "stable"
        )
        return {
            "avg_interest": round(avg, 1),
            "recent_interest": round(recent_3mo, 1),
            "older_interest": round(older_3mo, 1),
            "trend": trend_direction,
            "geo": geo,
        }
    except Exception as exc:
        print(f"  Google Trends fetch failed: {exc}")
        return None


def format_visits(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n}"


def format_duration(s: int) -> str:
    m, sec = divmod(s, 60)
    return f"{m}m {sec}s"


def print_domain_report(domain: str, show_trends: bool = True) -> None:
    print(f"\n{'=' * 70}")
    print(f"Traffic estimate for: {domain}")
    print(f"{'=' * 70}")

    # ---- Similarweb ----
    print("\n[1/2] Fetching Similarweb public data ...")
    sw_raw = fetch_similarweb(domain)
    if sw_raw:
        sw = summarize_similarweb(sw_raw)
        print(f"\n  Estimated monthly visits:  ~{format_visits(sw['estimated_visits'])}")
        print(f"  Global rank:               #{sw['global_rank']:,}" if sw['global_rank'] else "  Global rank: n/a")
        print(f"  Country rank:              #{sw['country_rank']:,}" if sw['country_rank'] else "")
        print(f"  Category:                  {sw['category']}")
        print(f"  Bounce rate:               {sw['bounce_rate_pct']}%")
        print(f"  Pages per visit:           {sw['pages_per_visit']}")
        print(f"  Avg visit duration:        {format_duration(sw['avg_visit_seconds'])}")

        if sw["monthly_history"]:
            print("\n  Monthly visits (history):")
            for month, visits in list(sw["monthly_history"].items())[-6:]:
                print(f"    {month}: {format_visits(int(visits))}")

        if sw["top_countries"]:
            print("\n  Top 5 countries by traffic share:")
            for c in sw["top_countries"]:
                country_code = c.get("CountryCode") or c.get("Country")
                share = c.get("Value", 0) * 100
                print(f"    {country_code}: {share:.1f}%")

        if sw["traffic_sources"]:
            print("\n  Traffic source breakdown:")
            for src, val in sw["traffic_sources"].items():
                print(f"    {src:20s}: {val * 100:5.1f}%")
    else:
        print("  (no Similarweb data available for this domain)")

    # ---- Google Trends ----
    if show_trends:
        # Use brand name (domain minus TLD) as search keyword
        keyword = domain.split(".")[0]
        print(f"\n[2/2] Fetching Google Trends for '{keyword}' (CZ, last 12 months) ...")
        gt = fetch_google_trends(keyword, geo="CZ")
        if gt:
            print(f"\n  Avg search interest (0-100): {gt['avg_interest']}")
            print(f"  Recent 3 months avg:         {gt['recent_interest']}")
            print(f"  Earlier period avg:          {gt['older_interest']}")
            print(f"  Trend:                       {gt['trend']}")
        else:
            print("  (no trend data)")


def main():
    parser = argparse.ArgumentParser(description="Estimate website monthly visitors for free.")
    parser.add_argument("--domain", default="freshlabels.cz", help="Domain to analyze")
    parser.add_argument("--compare", default="", help="Comma-separated list of competitor domains")
    parser.add_argument("--no-trends", action="store_true", help="Skip Google Trends")
    args = parser.parse_args()

    print(f"\nWebsite Traffic Estimator — generated {datetime.now():%Y-%m-%d %H:%M}")
    print("Data sources: Similarweb (public), Google Trends (pytrends)")
    print("Note: Similarweb numbers are directional estimates, not exact counts.")

    print_domain_report(args.domain, show_trends=not args.no_trends)

    if args.compare:
        comps = [c.strip() for c in args.compare.split(",") if c.strip()]
        for comp in comps:
            print_domain_report(comp, show_trends=not args.no_trends)

    print(f"\n{'=' * 70}")
    print("Methodology notes:")
    print("  • Similarweb estimates via their global panel + ISP data (±20% typical).")
    print("  • For a Czech site, the CZ-only slice = estimated_visits × CZ share.")
    print("  • Cross-check with Google Trends: rising interest usually → rising visits.")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    sys.exit(main() or 0)
