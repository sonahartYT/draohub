"""
Company career page scraper — scrapes career pages of major Nigerian
upstream operators using Apify's web scraper with generic extraction.
"""

import logging
from src.config import COMPANY_CAREER_URLS
from src.scrapers.base import get_apify_client, run_web_scraper, stagger

logger = logging.getLogger(__name__)

# Generic page function that extracts any links that look like job postings.
# Each company site is different, so this casts a wide net and filters by keywords.
PAGE_FUNCTION = """
async function pageFunction(context) {
    const { request, jQuery: $ } = context;
    const jobs = [];
    const oilKeywords = /engineer|manager|analyst|officer|superintendent|coordinator|technician|supervisor|specialist|advisor|planner|inspector|lead|director|procurement|supply|logistics|HSE|drilling|reservoir|production|pipeline|subsea/i;

    // Strategy: find all links that look like job postings
    $('a').each(function () {
        const $a = $(this);
        const href = $a.attr('href') || '';
        const text = $a.text().trim();

        // Skip navigation, social links, etc.
        if (!text || text.length < 10 || text.length > 200) return;
        if (href.includes('linkedin.com') || href.includes('facebook.com')) return;
        if (href === '#' || href === '/') return;

        // Check if the link text looks like a job title
        if (oilKeywords.test(text) || href.includes('job') || href.includes('career') || href.includes('vacancy')) {
            // Try to find a parent container with more info
            const $parent = $a.closest('div, li, tr, article').first();
            const allText = $parent.text().trim();

            jobs.push({
                title: text,
                company: '',  // Will be filled by the Python code from COMPANY_CAREER_URLS keys
                location: 'Nigeria',
                date_posted: '',
                apply_url: href,
                description: allText.substring(0, 500),
            });
        }
    });

    return jobs;
}
"""


def scrape() -> list[dict]:
    client = get_apify_client()
    all_jobs = []

    for company_name, career_url in COMPANY_CAREER_URLS.items():
        logger.info(f"Company page: {company_name} ({career_url})")
        items = run_web_scraper(client, [career_url], PAGE_FUNCTION, max_pages=2)

        for item in items:
            apply_url = item.get("apply_url", "")
            # Make relative URLs absolute
            if apply_url and not apply_url.startswith("http"):
                # Extract base domain from career_url
                from urllib.parse import urlparse
                parsed = urlparse(career_url)
                base = f"{parsed.scheme}://{parsed.netloc}"
                apply_url = f"{base}{apply_url}" if apply_url.startswith("/") else f"{base}/{apply_url}"

            all_jobs.append({
                "job_title": (item.get("title") or "").strip(),
                "company": company_name,
                "location": (item.get("location") or "Nigeria").strip(),
                "date_posted": item.get("date_posted") or None,
                "description": item.get("description") or None,
                "apply_url": apply_url or None,
                "source": "company_career_page",
            })

        logger.info(f"Company page: {company_name} yielded {len(items)} potential listings")
        stagger()

    return all_jobs
