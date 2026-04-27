"""
Jobberman.com scraper using requests + BeautifulSoup.

Selectors confirmed against live HTML on 2026-04-16:
  Card root : div[data-cy="listing-cards-components"]
  Title/URL : a[data-cy="listing-title-link"]
  Company   : first p.text-blue-700.text-sm inside card
  Location  : first span.bg-brand-secondary-100 inside card
  Date      : p.text-sm.font-normal.text-gray-700.text-loading-animate
  Desc      : p containing "md:text-gray-500" class
  Pagination: ?q=...&l=Nigeria&page=N  (up to MAX_PAGES)
"""
import logging
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE = "jobberman"
BASE_URL = "https://www.jobberman.com/jobs"
MAX_PAGES = 3
DELAY_SECONDS = 2
DETAIL_DELAY = 1
MAX_DETAIL_FETCHES = 40
SHORT_DESC_THRESHOLD = 250

SEARCH_TERMS = [
    "oil and gas",
    "upstream",
    "supply chain",
    "drilling",
    "procurement",
    "HSE",
    "engineering",
    "project management",
    "graduate trainee",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_full_description(url: str) -> str | None:
    """
    Fetch the Jobberman detail page and return the full job description.
    The description lives in a div whose class list includes 'prose' and 'prose-gray'.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        el = soup.find(
            "div",
            class_=lambda c: c and "prose" in c and "prose-gray" in c,
        )
        if el:
            return el.get_text(separator="\n", strip=True) or None
    except Exception as exc:
        logger.debug("jobberman detail fetch failed [%s]: %s", url, exc)
    return None


def _parse_card(card) -> dict:
    """Extract fields from a single listing card."""
    title_a = card.find("a", attrs={"data-cy": "listing-title-link"})
    title = title_a.get_text(strip=True) if title_a else None
    apply_url = title_a["href"] if title_a and title_a.get("href") else None

    company_p = card.find(
        "p", class_=lambda c: c and "text-blue-700" in c and "text-sm" in c
    )
    company = company_p.get_text(strip=True) if company_p else None

    location_spans = card.find_all(
        "span", class_=lambda c: c and "bg-brand-secondary-100" in c
    )
    location = location_spans[0].get_text(strip=True) if location_spans else None

    date_p = card.find(
        "p",
        class_=lambda c: c and "text-gray-700" in c and "text-loading-animate" in c and "text-sm" in c,
    )
    date_posted = date_p.get_text(strip=True) if date_p else None

    desc_p = card.find(
        "p",
        class_=lambda c: c and "md:text-gray-500" in c,
    )
    description = desc_p.get_text(strip=True) if desc_p else None

    return {
        "title": title,
        "company": company,
        "location": location,
        "date_posted": date_posted,
        "description": description,
        "apply_url": apply_url,
    }


def _scrape_page(term: str, page: int) -> tuple[list[dict], bool]:
    """
    Fetch one page of results.
    Returns (jobs, has_results) — has_results=False means stop paginating.
    """
    params = {"q": term, "l": "Nigeria", "page": page}
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("jobberman request failed [%s page %d]: %s", term, page, exc)
        return [], False

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.find_all("div", attrs={"data-cy": "listing-cards-components"})
    if not cards:
        return [], False

    return [_parse_card(c) for c in cards], True


def _scrape_term(term: str) -> list[dict]:
    """Scrape up to MAX_PAGES for a single search term."""
    jobs: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        page_jobs, has_results = _scrape_page(term, page)
        jobs.extend(page_jobs)
        logger.debug("jobberman [%s page %d]: %d results", term, page, len(page_jobs))
        if not has_results:
            break
        if page < MAX_PAGES:
            time.sleep(DELAY_SECONDS)
    return jobs


def run() -> tuple[list[dict], list[str]]:
    """
    Scrape Jobberman for all search terms, up to 3 pages each.
    Returns (jobs, failed_terms).
    """
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()
    failed_terms: list[str] = []

    logger.info("jobberman_scraper: starting %d search terms", len(SEARCH_TERMS))

    for i, term in enumerate(SEARCH_TERMS, 1):
        logger.info("jobberman [%d/%d]: %s", i, len(SEARCH_TERMS), term)
        results = _scrape_term(term)

        new_count = 0
        for job in results:
            url = job.get("apply_url") or ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            all_jobs.append(job)
            new_count += 1

        if not results:
            failed_terms.append(term)

        logger.info(
            "jobberman [%d/%d]: %d new (running total: %d)",
            i, len(SEARCH_TERMS), new_count, len(all_jobs),
        )

        if i < len(SEARCH_TERMS):
            time.sleep(DELAY_SECONDS)

    logger.info(
        "jobberman_scraper: finished search phase — %d jobs collected, %d failed terms",
        len(all_jobs), len(failed_terms),
    )

    # ── Detail-page enrichment ────────────────────────────────────────────────
    needs_detail = [
        j for j in all_jobs
        if j.get("apply_url") and len(j.get("description") or "") < SHORT_DESC_THRESHOLD
    ]
    to_fetch = needs_detail[:MAX_DETAIL_FETCHES]
    if to_fetch:
        logger.info("jobberman_scraper: enriching %d short-desc jobs with detail pages", len(to_fetch))
        enriched = 0
        for job in to_fetch:
            full = _fetch_full_description(job["apply_url"])
            if full and len(full) > len(job.get("description") or ""):
                job["description"] = full
                enriched += 1
            time.sleep(DETAIL_DELAY)
        logger.info("jobberman_scraper: enriched %d/%d jobs", enriched, len(to_fetch))

    return all_jobs, failed_terms
