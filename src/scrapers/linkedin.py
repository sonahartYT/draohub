"""
LinkedIn scraper — uses the dedicated Apify LinkedIn Jobs Scraper actor.
Constructs search URLs filtered to Nigeria and the past week.
"""

import logging
import urllib.parse
from src.config import get_all_queries, MAX_ITEMS_PER_QUERY
from src.scrapers.base import get_apify_client, stagger

logger = logging.getLogger(__name__)
ACTOR_ID = "curious_coder/linkedin-jobs-scraper"


def _build_url(query: str) -> str:
    encoded = urllib.parse.quote(query)
    return (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={encoded}&location=Nigeria&f_TPR=r604800"
    )


def scrape() -> list[dict]:
    client = get_apify_client()
    all_jobs = []

    for query in get_all_queries():
        logger.info(f"LinkedIn: '{query}'")
        try:
            run = client.actor(ACTOR_ID).call(run_input={
                "urls": [_build_url(query)],
                "maxItems": MAX_ITEMS_PER_QUERY,
            })
            items = client.dataset(run["defaultDatasetId"]).list_items().items

            for item in items:
                all_jobs.append({
                    "job_title": (item.get("title") or "").strip(),
                    "company": (item.get("companyName") or "").strip(),
                    "location": (item.get("location") or "").strip(),
                    "date_posted": item.get("postedAt") or None,
                    "description": item.get("descriptionText") or None,
                    "apply_url": item.get("applyUrl") or item.get("link") or None,
                    "source": "linkedin",
                })

            logger.info(f"LinkedIn: {len(items)} results for '{query}'")
        except Exception as e:
            logger.error(f"LinkedIn failed for '{query}': {e}")

        stagger()

    return all_jobs
