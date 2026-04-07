"""
MyJobMag Nigeria scraper — uses Apify web scraper with updated selectors.
MyJobMag uses server-rendered HTML which makes scraping more reliable.
"""

import logging
from src.config import get_all_queries
from src.scrapers.base import get_apify_client, run_web_scraper, stagger

logger = logging.getLogger(__name__)

# MyJobMag renders job listings in a clean list structure.
PAGE_FUNCTION = """
async function pageFunction(context) {
    const { request, jQuery: $ } = context;
    const jobs = [];

    // MyJobMag job cards are in ul.job-list li or div.job-info blocks
    const cards = $('ul.job-list li, div.job-info, div.mag-b, li.mag-b, div[class*="job-item"]');

    cards.each(function () {
        const $el = $(this);
        const titleEl = $el.find('a[class*="job-url"], h2 a, a[href*="/job/"]').first();

        const title = titleEl.text().trim();
        if (!title) return;

        const href = titleEl.attr('href') || '';
        const company = $el.find('span[class*="company"], div[class*="company"], a[class*="company"]').first().text().trim()
                     || $el.find('li:contains("Company") span, div > a[href*="/company/"]').first().text().trim();
        const location = $el.find('span[class*="location"], li:contains("Location") span, span:contains("Lagos"), span:contains("Nigeria")').first().text().trim();
        const date = $el.find('time, span[class*="date"], li:contains("Date") span').first().text().trim();
        const desc = $el.find('p, div[class*="desc"], div[class*="snippet"]').first().text().trim();

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
        logger.info(f"MyJobMag: '{query}'")
        url = f"https://www.myjobmag.com/search/jobs?q={query.replace(' ', '+')}"
        items = run_web_scraper(client, [url], PAGE_FUNCTION, max_pages=3)

        for item in items:
            apply_url = item.get("apply_url", "")
            if apply_url and not apply_url.startswith("http"):
                apply_url = f"https://www.myjobmag.com{apply_url}"

            all_jobs.append({
                "job_title": (item.get("title") or "").strip(),
                "company": (item.get("company") or "").strip(),
                "location": (item.get("location") or "").strip(),
                "date_posted": item.get("date_posted") or None,
                "description": item.get("description") or None,
                "apply_url": apply_url or None,
                "source": "myjobmag",
            })

        logger.info(f"MyJobMag: {len(items)} results for '{query}'")
        stagger()

    return all_jobs
