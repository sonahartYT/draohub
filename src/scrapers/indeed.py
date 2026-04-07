"""
Indeed scraper — uses the Apify Indeed Scraper actor, filtered to Nigeria.
"""

import logging
from src.config import get_all_queries, MAX_ITEMS_PER_QUERY
from src.scrapers.base import get_apify_client, stagger

logger = logging.getLogger(__name__)
ACTOR_ID = "misceres/indeed-scraper"


def scrape() -> list[dict]:
    client = get_apify_client()
    all_jobs = []

    for query in get_all_queries():
        logger.info(f"Indeed: '{query}'")
        try:
            run = client.actor(ACTOR_ID).call(run_input={
                "position": query,
                "country": "NG",
                "location": "Nigeria",
                "maxItems": MAX_ITEMS_PER_QUERY,
            })
            items = client.dataset(run["defaultDatasetId"]).list_items().items

            for item in items:
                all_jobs.append({
                    "job_title": (item.get("positionName") or item.get("title") or "").strip(),
                    "company": (item.get("company") or "").strip(),
                    "location": (item.get("location") or "").strip(),
                    "date_posted": item.get("date") or item.get("postedAt") or None,
                    "description": item.get("description") or None,
                    "apply_url": item.get("url") or item.get("externalUrl") or None,
                    "source": "indeed",
                })

            logger.info(f"Indeed: {len(items)} results for '{query}'")
        except Exception as e:
            logger.error(f"Indeed failed for '{query}': {e}")

        stagger()

    return all_jobs
