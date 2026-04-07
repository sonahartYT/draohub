"""
Central configuration — loads environment variables and defines constants.
All other modules import from here instead of reading .env directly.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
APIFY_API_KEY = os.getenv("APIFY_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- Structured Search Queries ---
# Organized by domain so we can prioritise or weight categories later.
SEARCH_QUERIES = {
    "supply_chain": [
        "supply chain oil and gas Nigeria",
        "procurement upstream Nigeria",
        "logistics oil and gas Nigeria",
        "materials management upstream",
        "vendor management oil and gas",
        "inventory control upstream Nigeria",
    ],
    "engineering": [
        "upstream engineer Nigeria",
        "drilling engineer Nigeria",
        "production engineer oil and gas Nigeria",
        "reservoir engineer Nigeria",
        "facilities engineer upstream",
        "subsurface engineer Nigeria",
    ],
    "finance": [
        "oil and gas finance Nigeria",
        "upstream commercial analyst",
        "energy analyst Nigeria",
        "petroleum economist Nigeria",
        "oil and gas project finance",
    ],
    "project_management": [
        "project manager oil and gas Nigeria",
        "project engineer upstream Nigeria",
        "PMC oil and gas Nigeria",
    ],
    "hse": [
        "HSE officer oil and gas Nigeria",
        "safety engineer upstream Nigeria",
        "QHSE oil and gas Nigeria",
    ],
    "general": [
        "upstream oil and gas Nigeria",
        "petroleum industry Nigeria",
        "IOC jobs Nigeria",
        "NOC jobs Nigeria",
        "oil field jobs Nigeria",
    ],
}


def get_all_queries() -> list[str]:
    """Flatten all query groups into a single list."""
    return [q for group in SEARCH_QUERIES.values() for q in group]


# --- Company Career Pages ---
# Major Nigerian upstream operators whose career pages we scrape directly.
COMPANY_CAREER_URLS = {
    "NNPC": "https://careers.nnpcgroup.com/jobs",
    "Shell Nigeria": "https://www.shell.com.ng/careers/experienced-professionals.html",
    "TotalEnergies Nigeria": "https://careers.totalenergies.com/en/search-results?keywords=&location=Nigeria",
    "Chevron Nigeria": "https://careers.chevron.com/search-jobs/Nigeria",
    "ExxonMobil Nigeria": "https://jobs.exxonmobil.com/search/?q=&locationsearch=Nigeria",
    "Seplat Energy": "https://seplatenergy.com/people-culture/current-opportunities/",
    "Oando": "https://www.oandoplc.com/careers/",
    "Sahara Group": "https://www.sahara-group.com/careers",
}

# --- Apify Actor IDs ---
APIFY_ACTORS = {
    "linkedin": "curious_coder/linkedin-jobs-scraper",
    "indeed": "misceres/indeed-scraper",
    "web_scraper": "apify/web-scraper",
}

# --- Scraper Settings ---
SCRAPE_HOUR_UTC = 7
REQUEST_DELAY_SECONDS = 3       # Delay between source requests to avoid rate limiting
MAX_ITEMS_PER_QUERY = 25        # Max results per query per source
LOG_DIR = "logs"                # Directory for daily scrape logs
