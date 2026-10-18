import logging
from datetime import datetime
from threading import Lock
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

import config
from scheduler import run_news_workflow
from news_service import NewsAPIError


logger = logging.getLogger(__name__)
INTERVAL_SECONDS = {
    "1_minute": 60,
    "5_minutes": 5 * 60,
    "1_hour": 60 * 60,
    "1_day": 24 * 60 * 60,
}
INTERVAL_LABELS = {
    "1_minute": "Every 1 minute",
    "5_minutes": "Every 5 minutes",
    "1_hour": "Every 1 hour",
    "1_day": "Every 1 day",
}

_lock = Lock()
_scheduler = None
_state = {
    "running": False,
    "interval": None,
    "last_run_at": None,
    "last_run_id": 0,
    "last_attempt_at": None,
    "run_in_progress": False,
    "last_success": None,
    "last_error": None,
}


def _run_interval_workflow():
    with _lock:
        _state["run_in_progress"] = True
        _state["last_attempt_at"] = datetime.now(
            ZoneInfo(config.NEWS_SCHEDULE_TIMEZONE)
        ).isoformat()

    try:
        result = run_news_workflow()
    except Exception as error:
        logger.error(
            "Interval news workflow failed (%s).",
            type(error).__name__,
        )
        with _lock:
            _state["run_in_progress"] = False
            _state["last_run_at"] = _state["last_attempt_at"]
            _state["last_run_id"] += 1
            if isinstance(error, NewsAPIError):
                _state["last_error"] = str(error)
            else:
                _state["last_error"] = (
                    "Workflow failed because of a database or internal error. "
                    "Check the API server terminal for details."
                )
        raise

    success = {
        "fetched": result["fetched"],
        "inserted": result["inserted"],
        "duplicates": result["duplicates"],
        "briefing_date": result["briefing"]["briefing_date"],
    }
    with _lock:
        _state["run_in_progress"] = False
        _state["last_run_at"] = _state["last_attempt_at"]
        _state["last_run_id"] += 1
        _state["last_success"] = success
        _state["last_error"] = None
    return result


def get_interval_status():
    with _lock:
        status = dict(_state)
        if _scheduler is not None and _scheduler.running:
            job = _scheduler.get_job("dashboard_news_refresh")
            status["next_run_at"] = (
                job.next_run_time.isoformat()
                if job and job.next_run_time
                else None
            )
        else:
            status["next_run_at"] = None
        status["interval_label"] = (
            INTERVAL_LABELS.get(status["interval"])
            if status["interval"]
            else None
        )
        return status


def start_interval_schedule(interval):
    global _scheduler

    if interval not in INTERVAL_SECONDS:
        raise ValueError(
            "Choose one of: 1_minute, 5_minutes, 1_hour, or 1_day."
        )

    with _lock:
        if _scheduler is None or not _scheduler.running:
            _scheduler = BackgroundScheduler(
                timezone=ZoneInfo(config.NEWS_SCHEDULE_TIMEZONE)
            )
            _scheduler.start()

        _scheduler.add_job(
            _run_interval_workflow,
            trigger="interval",
            seconds=INTERVAL_SECONDS[interval],
            id="dashboard_news_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
            next_run_time=datetime.now(
                ZoneInfo(config.NEWS_SCHEDULE_TIMEZONE)
            ),
        )
        _state.update(
            {
                "running": True,
                "interval": interval,
                "last_run_at": None,
                "last_run_id": 0,
                "last_attempt_at": None,
                "run_in_progress": False,
                "last_success": None,
                "last_error": None,
            }
        )

    logger.info("Dashboard news refresh started: %s.", INTERVAL_LABELS[interval])
    return get_interval_status()


def stop_interval_schedule():
    global _scheduler

    with _lock:
        if _scheduler is not None:
            if _scheduler.running:
                _scheduler.remove_job("dashboard_news_refresh")
                _scheduler.shutdown(wait=False)
            _scheduler = None
        _state.update(
            {
                "running": False,
                "interval": None,
                "next_run_at": None,
                "interval_label": None,
            }
        )

    logger.info("Dashboard news refresh stopped.")
    return get_interval_status()
