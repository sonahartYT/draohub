"""
MyJobMag.com scraper using requests + BeautifulSoup.

Selectors confirmed against live HTML on 2026-04-16:
  Search URL   : /search/jobs?q={term}&currentpage={N}
  Card root    : ul (parent of li.mag-b)
  Title + URL  : a[href^="/job/"] — text is "Title at Company"
  Company      : split " at " from title text (last token)
  Description  : li.job-desc text
  Date         : li#job-date text
  Location     : not present on search page — set to null
  Pagination   : ?currentpage=N up to MAX_PAGES
"""
import logging
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE = "myjobmag"

_MONTHS = {
    "january","february","march","april","may","june",
    "july","august","september","october","november","december",
}

def _normalise_date(raw: str | None) -> str | None:
    """
    Append current year if date looks like 'DD Month' or 'Month DD' without a year.
    e.g. '11 March' → '11 March 2026', '3 days ago' → '3 days ago' (unchanged).
    """
    if not raw:
        return None
    # If it already contains a 4-digit year, leave it alone
    if re.search(r'\b20\d{2}\b', raw):
        return raw
    # If it contains a month name but no year, append current year
    if any(m in raw.lower() for m in _MONTHS):
        return f"{raw} {datetime.now().year}"
    return raw
BASE_URL = "https://www.myjobmag.com/search/jobs"
MAX_PAGES = 3
DELAY_SECONDS = 2

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


def _parse_card(card) -> dict:
    """Extract fields from a single card (ul containing li.mag-b)."""
    title_a = card.find("a", href=lambda h: h and h.startswith("/job/"))
    if not title_a:
        return {}

    raw_title = title_a.get_text(strip=True)
    # Title text is "Job Title at Company Name"
    if " at " in raw_title:
        parts = raw_title.rsplit(" at ", 1)
        title = parts[0].strip()
        company = parts[1].strip()
    else:
        title = raw_title
        company = None

    href = title_a.get("href", "")
    apply_url = f"https://www.myjobmag.com{href}" if href else None

    desc_li = card.find("li", class_="job-desc")
    description = desc_li.get_text(strip=True) if desc_li else None

    date_li = card.find("li", id="job-date")
    date_raw = date_li.get_text(strip=True) if date_li else None
    # MyJobMag sometimes returns "11 March" without a year — append current year
    date_posted = _normalise_date(date_raw)

    return {
        "title": title,
        "company": company,
        "location": None,        # not available in search results
        "date_posted": date_posted,
        "description": description,
        "apply_url": apply_url,
    }


def _scrape_page(term: str, page: int) -> tuple[list[dict], bool]:
    """
    Fetch one page of results.
    Returns (jobs, has_results).
    """
    params = {"q": term, "currentpage": page}
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("myjobmag request failed [%s page %d]: %s", term, page, exc)
        return [], False

    soup = BeautifulSoup(resp.text, "html.parser")

    # Card roots are ul elements that directly contain a li.mag-b
    mag_b_items = soup.find_all("li", class_="mag-b")
    if not mag_b_items:
        return [], False

    cards = [li.parent for li in mag_b_items if li.parent]
    jobs = []
    for card in cards:
        parsed = _parse_card(card)
        if parsed.get("title"):
            jobs.append(parsed)
    return jobs, True


def _scrape_term(term: str) -> list[dict]:
    """Scrape up to MAX_PAGES for a single search term."""
    jobs: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        page_jobs, has_results = _scrape_page(term, page)
        jobs.extend(page_jobs)
        logger.debug("myjobmag [%s page %d]: %d results", term, page, len(page_jobs))
        if not has_results:
            break
        if page < MAX_PAGES:
            time.sleep(DELAY_SECONDS)
    return jobs


def run() -> tuple[list[dict], list[str]]:
    """
    Scrape MyJobMag for all search terms, up to 3 pages each.
    Returns (jobs, failed_terms).
    """
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()
    failed_terms: list[str] = []

    logger.info("myjobmag_scraper: starting %d search terms", len(SEARCH_TERMS))

    for i, term in enumerate(SEARCH_TERMS, 1):
        logger.info("myjobmag [%d/%d]: %s", i, len(SEARCH_TERMS), term)
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
            "myjobmag [%d/%d]: %d new (running total: %d)",
            i, len(SEARCH_TERMS), new_count, len(all_jobs),
        )

        if i < len(SEARCH_TERMS):
            time.sleep(DELAY_SECONDS)

    logger.info(
        "myjobmag_scraper: finished — %d jobs collected, %d failed terms",
        len(all_jobs), len(failed_terms),
    )
    return all_jobs, failed_terms
