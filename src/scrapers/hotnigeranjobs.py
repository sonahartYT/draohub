"""
HotNigerianJobs scraper — uses Apify web scraper.
Site is server-rendered, making extraction straightforward.
"""

import logging
from src.config import get_all_queries
from src.scrapers.base import get_apify_client, run_web_scraper, stagger

logger = logging.getLogger(__name__)

PAGE_FUNCTION = """
async function pageFunction(context) {
    const { request, jQuery: $ } = context;
    const jobs = [];

    // HotNigerianJobs uses a simple blog-like listing of job posts
    const cards = $('div.post, article, div.job-listing, div[class*="entry"]');

    cards.each(function () {
        const $el = $(this);
        const titleEl = $el.find('h2 a, h3 a, a[class*="title"]').first();

        const title = titleEl.text().trim();
        if (!title) return;

        const href = titleEl.attr('href') || '';
        const meta = $el.find('span[class*="meta"], div[class*="meta"], p.entry-meta').first().text().trim();
        const desc = $el.find('div[class*="content"], div[class*="summary"], p.entry-content').first().text().trim();

        // Try to extract company from title or meta (format: "Job Title at Company")
        let company = '';
        const atMatch = title.match(/(?:at|@)\\s+(.+?)(?:\\s*[-–|]|$)/i);
        if (atMatch) company = atMatch[1].trim();

        jobs.push({
            title: title,
            company: company,
            location: 'Nigeria',
            date_posted: meta,
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
        logger.info(f"HotNigerianJobs: '{query}'")
        url = f"https://www.hotnigerianjobs.com/search?q={query.replace(' ', '+')}"
        items = run_web_scraper(client, [url], PAGE_FUNCTION, max_pages=2)

        for item in items:
            apply_url = item.get("apply_url", "")
            if apply_url and not apply_url.startswith("http"):
                apply_url = f"https://www.hotnigerianjobs.com{apply_url}"

            all_jobs.append({
                "job_title": (item.get("title") or "").strip(),
                "company": (item.get("company") or "").strip(),
                "location": (item.get("location") or "Nigeria").strip(),
                "date_posted": item.get("date_posted") or None,
                "description": item.get("description") or None,
                "apply_url": apply_url or None,
                "source": "hotnigerianjobs",
            })

        logger.info(f"HotNigerianJobs: {len(items)} results for '{query}'")
        stagger()

    return all_jobs
