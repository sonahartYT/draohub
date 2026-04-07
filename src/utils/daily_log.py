"""
Daily scrape log — writes a structured log file for each pipeline run.
Saved to logs/YYYY-MM-DD.log with per-source stats.
"""

import os
import json
from datetime import datetime, timezone
from src.config import LOG_DIR


def get_log_path() -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"{date_str}.log")


class ScrapeLog:
    """Accumulates per-source stats and writes a summary at the end."""

    def __init__(self):
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.sources: list[dict] = []

    def add_source(self, name: str, scraped: int, inserted: int, updated: int,
                   skipped: int, error: str = None):
        self.sources.append({
            "source": name,
            "scraped": scraped,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "error": error,
        })

    def summary(self) -> dict:
        total_scraped = sum(s["scraped"] for s in self.sources)
        total_inserted = sum(s["inserted"] for s in self.sources)
        total_updated = sum(s["updated"] for s in self.sources)
        return {
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_scraped": total_scraped,
            "total_inserted": total_inserted,
            "total_updated": total_updated,
            "sources": self.sources,
        }

    def write(self):
        path = get_log_path()
        summary = self.summary()
        with open(path, "a") as f:
            f.write(json.dumps(summary, indent=2) + "\n\n")
        return summary
