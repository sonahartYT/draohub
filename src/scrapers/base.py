"""
Shared scraper utilities — Apify client helper, stagger delay, web scraper runner.
"""

import time
import logging
from apify_client import ApifyClient
from src.config import APIFY_API_KEY, REQUEST_DELAY_SECONDS

logger = logging.getLogger(__name__)


def get_apify_client() -> ApifyClient:
    return ApifyClient(APIFY_API_KEY)


def stagger():
    """Sleep between requests to avoid rate limiting."""
    time.sleep(REQUEST_DELAY_SECONDS)


def run_web_scraper(client: ApifyClient, urls: list[str], page_function: str,
                    max_pages: int = 3) -> list[dict]:
    """
    Run Apify's generic web-scraper actor and return the raw dataset items.
    Handles errors gracefully — returns empty list on failure.
    """
    run_input = {
        "startUrls": [{"url": u} for u in urls],
        "pageFunction": page_function,
        "proxyConfiguration": {"useApifyProxy": True},
        "maxPagesPerCrawl": max_pages,
    }
    try:
        run = client.actor("apify/web-scraper").call(run_input=run_input)
        items = client.dataset(run["defaultDatasetId"]).list_items().items
        # Flatten: web scraper returns pageFunction result per page (could be list or dict)
        flat = []
        for item in items:
            if isinstance(item, list):
                flat.extend(item)
            elif isinstance(item, dict):
                flat.append(item)
        return flat
    except Exception as e:
        logger.error(f"Web scraper failed for {urls}: {e}")
        return []
