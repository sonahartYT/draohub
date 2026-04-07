"""
DracoHub Careers — Daily Scheduler

Runs the scrape pipeline every day at 7:00 AM UTC.
Start with:  python run_scheduler.py

For production, you'd typically use a cron job or a cloud scheduler
(e.g., GitHub Actions, Railway cron, or Render cron) instead of this
long-running process. This script is useful for local development
and simple VPS deployments.
"""

import time
import logging
import schedule

from src.main import run_pipeline
from src.config import SCRAPE_HOUR_UTC

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler")


def main():
    schedule_time = f"{SCRAPE_HOUR_UTC:02d}:00"
    schedule.every().day.at(schedule_time).do(run_pipeline)
    logger.info(f"Scheduler started. Pipeline will run daily at {schedule_time} UTC.")
    logger.info("Press Ctrl+C to stop.")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
