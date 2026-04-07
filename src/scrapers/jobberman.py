"""
Jobberman Nigeria scraper — uses Apify web scraper with updated CSS selectors.
Jobberman uses a React app; selectors target their current card structure.
"""

import logging
from src.config import get_all_queries
from src.scrapers.base import get_apify_client, run_web_scraper, stagger

logger = logging.getLogger(__name__)

# Updated page function targeting Jobberman's current DOM structure.
# Jobberman renders job cards in a list; each card has structured data attributes.
PAGE_FUNCTION = """
async function pageFunction(context) {
    const { request, jQuery: $ } = context;
    const jobs = [];

    // Jobberman uses various card layouts — try multiple selectors
    const cards = $('div.mx-5 > div, div[class*="JobCard"], article, div.relative.rounded-lg');

    cards.each(function () {
        const $el = $(this);
        // Title: look for the most prominent link
        const titleEl = $el.find('a p.text-lg, a h2, a[href*="/jobs/"] p, a[href*="/jobs/"] span.font-bold').first();
        const linkEl = $el.find('a[href*="/jobs/"]').first();

        const title = titleEl.text().trim() || linkEl.text().trim();
        if (!title) return; // skip non-job elements

        const href = linkEl.attr('href') || '';
        const company = $el.find('p.text-sm, span[class*="company"], p:contains("Company")').first().text().trim();
        const location = $el.find('span:contains("Lagos"), span:contains("Nigeria"), span:contains("Port Harcourt"), p:contains("Location")').first().text().trim();
        const date = $el.find('time, span[class*="date"], span:contains("ago")').first().text().trim();
        const desc = $el.find('p.text-sm.text-gray, p[class*="description"], div[class*="snippet"]').first().text().trim();

        jobs.push({
            title: title,
            company: company,
            location: location || 'Nigeria',
            date_posted: date,
            apply_url: href,
            description: desc,
        });
    });

    return jobs;
}
"""


def scrape() -> list[dict]:
    client = get_apify_client()
    all_jobs = []

    for query in get_all_queries():
        logger.info(f"Jobberman: '{query}'")
        url = f"https://www.jobberman.com/jobs?q={query.replace(' ', '+')}"
        items = run_web_scraper(client, [url], PAGE_FUNCTION, max_pages=3)

        for item in items:
            apply_url = item.get("apply_url", "")
            if apply_url and not apply_url.startswith("http"):
                apply_url = f"https://www.jobberman.com{apply_url}"

            all_jobs.append({
                "job_title": (item.get("title") or "").strip(),
                "company": (item.get("company") or "").strip(),
                "location": (item.get("location") or "").strip(),
                "date_posted": item.get("date_posted") or None,
                "description": item.get("description") or None,
                "apply_url": apply_url or None,
                "source": "jobberman",
            })

        logger.info(f"Jobberman: {len(items)} results for '{query}'")
        stagger()

    return all_jobs
