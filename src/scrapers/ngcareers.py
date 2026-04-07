"""
NgCareers scraper — uses Apify web scraper for ngcareers.com.
"""

import logging
from src.config import get_all_queries
from src.scrapers.base import get_apify_client, run_web_scraper, stagger

logger = logging.getLogger(__name__)

PAGE_FUNCTION = """
async function pageFunction(context) {
    const { request, jQuery: $ } = context;
    const jobs = [];

    const cards = $('div.job-listing, div[class*="job-card"], article, div.listing-item, tr.job-row');

    cards.each(function () {
        const $el = $(this);
        const titleEl = $el.find('h2 a, h3 a, a[class*="title"], td a').first();

        const title = titleEl.text().trim();
        if (!title) return;

        const href = titleEl.attr('href') || '';
        const company = $el.find('span[class*="company"], a[class*="company"], td:nth-child(2)').first().text().trim();
        const location = $el.find('span[class*="location"], td:nth-child(3)').first().text().trim();
        const date = $el.find('time, span[class*="date"], td:last-child').first().text().trim();
        const desc = $el.find('p, div[class*="desc"]').first().text().trim();

        jobs.push({
            title: title,
            company: company,
            location: location || 'Nigeria',
            date_posted: date,
            apply_url: href,
            description: desc.substring(0, 500),
        });
    });

    return jobs;
}
"""


def scrape() -> list[dict]:
    client = get_apify_client()
    all_jobs = []

    for query in get_all_queries():
        logger.info(f"NgCareers: '{query}'")
        url = f"https://ngcareers.com/search?q={query.replace(' ', '+')}"
        items = run_web_scraper(client, [url], PAGE_FUNCTION, max_pages=2)

        for item in items:
            apply_url = item.get("apply_url", "")
            if apply_url and not apply_url.startswith("http"):
                apply_url = f"https://ngcareers.com{apply_url}"

            all_jobs.append({
                "job_title": (item.get("title") or "").strip(),
                "company": (item.get("company") or "").strip(),
                "location": (item.get("location") or "Nigeria").strip(),
                "date_posted": item.get("date_posted") or None,
                "description": item.get("description") or None,
                "apply_url": apply_url or None,
                "source": "ngcareers",
            })

        logger.info(f"NgCareers: {len(items)} results for '{query}'")
        stagger()

    return all_jobs
