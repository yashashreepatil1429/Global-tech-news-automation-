import logging
from time import perf_counter
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

import config
from briefing_service import generate_daily_briefing
from database import save_news_articles
from news_service import fetch_latest_news


logger = logging.getLogger(__name__)


def run_news_workflow():
    started_at = perf_counter()
    logger.info("Daily news workflow started.")

    try:
        articles = fetch_latest_news()
        if not isinstance(articles, list):
            raise TypeError("News collector must return a list of articles.")

        storage_result = save_news_articles(articles)
        briefing = generate_daily_briefing()
    except Exception as error:
        elapsed_seconds = perf_counter() - started_at
        logger.error(
            "Daily news workflow failed after %.2f seconds (%s).",
            elapsed_seconds,
            type(error).__name__,
        )
        raise

    elapsed_seconds = perf_counter() - started_at
    logger.info(
        "Daily news workflow completed in %.2f seconds: "
        "%d fetched, %d inserted, %d duplicates, briefing date %s.",
        elapsed_seconds,
        len(articles),
        storage_result["inserted"],
        storage_result["duplicates"],
        briefing["briefing_date"],
    )
    return {
        "fetched": len(articles),
        **storage_result,
        "briefing": briefing,
        "elapsed_seconds": elapsed_seconds,
    }


def create_scheduler():
    scheduler = BlockingScheduler(
        timezone=ZoneInfo(config.NEWS_SCHEDULE_TIMEZONE)
    )
    scheduler.add_job(
        run_news_workflow,
        trigger="cron",
        hour=config.NEWS_SCHEDULE_HOUR,
        minute=config.NEWS_SCHEDULE_MINUTE,
        timezone=ZoneInfo(config.NEWS_SCHEDULE_TIMEZONE),
        id="daily_global_tech_news",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler


def run_scheduler():
    scheduler = create_scheduler()
    logger.info(
        "Scheduler started: daily at %02d:%02d (%s).",
        config.NEWS_SCHEDULE_HOUR,
        config.NEWS_SCHEDULE_MINUTE,
        config.NEWS_SCHEDULE_TIMEZONE,
    )
    scheduler.start()
