"""
Company career pages scraper — runs weekly on Mondays at 6am UTC.

IMPORTANT — CURRENT LIMITATION:
All 12 company career pages below load their job listings via JavaScript
(Lever widgets, Oracle HCM, Workday, custom React apps). A plain
requests + BeautifulSoup scraper cannot execute JavaScript, so these
pages consistently return 0 static HTML job listings.

This module is built and wired into the pipeline so:
  1. The weekly GitHub Actions workflow runs it as designed.
  2. Each company page is fetched and logged — any that ever gains
     a static HTML fallback will be picked up automatically.
  3. Upgrading to Playwright is a one-line swap: replace _fetch_html()
     with a headless browser call and everything else stays the same.

To enable full JS-rendered scraping, install playwright and swap in:
    from playwright.sync_api import sync_playwright
    def _fetch_html(url):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            html = page.content()
            browser.close()
            return html
"""
import logging
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DELAY_SECONDS = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Per-company config.
# "source"      : value stored in the source/sources fields
# "url"         : careers page to fetch
# "job_link_pattern" : substring that distinguishes job-detail URLs from nav links
#                      (None = use generic heuristic)
COMPANIES = [
    {
        "source": "NNPC",
        "url": "https://careers.nnpcgroup.com",
        "job_link_pattern": None,
    },
    {
        "source": "Seplat Energy",
        "url": "https://www.seplatenergy.com/careers",
        "job_link_pattern": None,
    },
    {
        "source": "TotalEnergies Nigeria",
        "url": "https://careers.totalenergies.com/en/jobs?country=Nigeria",
        "job_link_pattern": "/jobs/",
    },
    {
        "source": "Shell Nigeria",
        "url": "https://www.shell.com.ng/careers.html",
        "job_link_pattern": None,
    },
    {
        "source": "Chevron Nigeria",
        "url": "https://careers.chevron.com",
        "job_link_pattern": "/jobs/",
    },
    {
        "source": "ExxonMobil Nigeria",
        "url": "https://jobs.exxonmobil.com",
        "job_link_pattern": "/jobs/",
    },
    {
        "source": "Oando",
        "url": "https://oandoplc.com/careers",
        "job_link_pattern": None,
    },
    {
        "source": "Heirs Energies",
        "url": "https://heirsenergies.com/careers",
        "job_link_pattern": None,
    },
    {
        "source": "Aradel Holdings",
        "url": "https://aradelholdings.com/careers",
        "job_link_pattern": None,
    },
    {
        "source": "Sahara Group",
        "url": "https://sahara-group.com/careers",
        "job_link_pattern": None,
    },
    {
        "source": "Renaissance Africa Energy",
        "url": "https://renaissanceafrica.com/careers",
        "job_link_pattern": None,
    },
    {
        "source": "Dangote Group",
        "url": "https://dangote.com/careers",
        "job_link_pattern": None,
    },
]

# Keywords used by the generic extractor to identify job-detail links
_JOB_KEYWORDS = [
    "job", "vacanc", "position", "opening", "role", "career",
    "engineer", "manager", "analyst", "officer", "technician",
]


def _fetch_html(url: str) -> str | None:
    """Fetch a URL and return the raw HTML string, or None on error."""
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=20,
            allow_redirects=True, verify=False,  # some company certs fail verification
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.error("fetch failed [%s]: %s", url, exc)
        return None


def _extract_jobs(html: str, company: dict) -> list[dict]:
    """
    Generic extractor: find <a> tags whose href or text contains job-like keywords.
    Returns a list of minimal job dicts (title + apply_url; other fields null).
    """
    soup = BeautifulSoup(html, "html.parser")
    pattern = company.get("job_link_pattern")
    base_url = company["url"].rstrip("/")
    source = company["source"]

    candidates = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)

        # Skip empty, nav, and anchor-only links
        if not text or not href or href.startswith("#"):
            continue
        if len(text) < 5 or len(text) > 150:
            continue

        # Match against explicit pattern or generic keywords
        href_lower = href.lower()
        text_lower = text.lower()
        if pattern:
            if pattern not in href_lower:
                continue
        else:
            if not any(kw in href_lower or kw in text_lower for kw in _JOB_KEYWORDS):
                continue

        # Resolve relative URLs
        if href.startswith("http"):
            apply_url = href
        elif href.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(company["url"])
            apply_url = f"{parsed.scheme}://{parsed.netloc}{href}"
        else:
            apply_url = f"{base_url}/{href}"

        candidates.append({
            "title": text,
            "company": source,
            "location": None,
            "date_posted": None,
            "description": None,
            "apply_url": apply_url,
        })

    # Deduplicate by URL
    seen = set()
    jobs = []
    for j in candidates:
        if j["apply_url"] not in seen:
            seen.add(j["apply_url"])
            jobs.append(j)

    return jobs


def _scrape_company(company: dict) -> list[dict]:
    """Fetch and extract jobs for one company."""
    source = company["source"]
    url = company["url"]
    logger.info("company_pages [%s]: fetching %s", source, url)

    html = _fetch_html(url)
    if html is None:
        return []

    jobs = _extract_jobs(html, company)

    if not jobs:
        logger.warning(
            "company_pages [%s]: 0 jobs extracted — page likely requires JavaScript. "
            "Upgrade to Playwright to scrape JS-rendered content.",
            source,
        )
    else:
        logger.info("company_pages [%s]: %d jobs found", source, len(jobs))

    return jobs


def run() -> tuple[list[dict], list[str]]:
    """
    Scrape all company career pages.
    Returns (jobs, failed_companies).
    """
    all_jobs: list[dict] = []
    failed_companies: list[str] = []

    logger.info("company_pages_scraper: starting %d companies", len(COMPANIES))

    for i, company in enumerate(COMPANIES, 1):
        source = company["source"]
        logger.info("company_pages [%d/%d]: %s", i, len(COMPANIES), source)

        jobs = _scrape_company(company)
        all_jobs.extend(jobs)

        if not jobs:
            failed_companies.append(source)

        if i < len(COMPANIES):
            time.sleep(DELAY_SECONDS)

    logger.info(
        "company_pages_scraper: finished — %d jobs collected across %d companies, "
        "%d returned 0 results",
        len(all_jobs), len(COMPANIES), len(failed_companies),
    )
    return all_jobs, failed_companies
