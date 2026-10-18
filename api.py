import logging
import re
from datetime import date, datetime

from bson import ObjectId
from flask import Flask, jsonify, render_template, request

import database
import interval_scheduler
from models import CATEGORY_KEYWORDS


app = Flask(__name__)
logger = logging.getLogger(__name__)
VALID_CATEGORIES = set(CATEGORY_KEYWORDS) | {"Other Technology"}


def _to_json_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            key: _to_json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_to_json_value(item) for item in value]
    return value


def _json_response(data, status=200):
    return jsonify(_to_json_value(data)), status


def _parse_pagination():
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError as error:
        raise ValueError("page and per_page must be whole numbers.") from error

    if page < 1:
        raise ValueError("page must be at least 1.")
    if not 1 <= per_page <= 100:
        raise ValueError("per_page must be between 1 and 100.")
    return page, per_page


def _parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", value
    ):
        raise ValueError("date must use YYYY-MM-DD format.")

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("date must use YYYY-MM-DD format.") from error


def _database_error_response(error):
    logger.error("API database operation failed (%s).", type(error).__name__)
    return _json_response(
        {"error": "Database unavailable. Please try again later."},
        status=503,
    )


@app.get("/health")
def health():
    try:
        database.check_database_connection()
    except RuntimeError as error:
        return _database_error_response(error)

    return _json_response({"status": "ok", "database": "connected"})


@app.get("/")
def dashboard():
    return render_template(
        "dashboard.html",
        categories=sorted(VALID_CATEGORIES),
    )


@app.get("/docs")
def api_documentation():
    return _json_response(
        {
            "service": "Daily Global Tech News Scheduler API",
            "endpoints": [
                {"method": "GET", "path": "/"},
                {"method": "GET", "path": "/health"},
                {"method": "GET", "path": "/automation"},
                {"method": "POST", "path": "/automation"},
                {"method": "DELETE", "path": "/automation"},
                {"method": "GET", "path": "/news?page=1&per_page=20"},
                {"method": "GET", "path": "/news/<id>"},
                {"method": "GET", "path": "/news/category/<category>"},
                {"method": "GET", "path": "/news/search?keyword=python"},
                {"method": "GET", "path": "/briefings?page=1&per_page=20"},
                {"method": "GET", "path": "/briefings?date=YYYY-MM-DD"},
                {"method": "GET", "path": "/briefings/<date>"},
            ],
        }
    )


@app.get("/automation")
def automation_status():
    return _json_response(interval_scheduler.get_interval_status())


@app.post("/automation")
def start_automation():
    settings = request.get_json(silent=True)
    if not isinstance(settings, dict):
        return _json_response(
            {"error": "Send a JSON object with an interval value."},
            status=400,
        )

    interval = settings.get("interval")
    try:
        status = interval_scheduler.start_interval_schedule(interval)
    except ValueError as error:
        return _json_response({"error": str(error)}, status=400)
    except Exception:
        logger.exception("Could not start dashboard news refresh.")
        return _json_response(
            {"error": "Could not start automatic news refresh."},
            status=503,
        )

    return _json_response(status)


@app.delete("/automation")
def stop_automation():
    try:
        status = interval_scheduler.stop_interval_schedule()
    except Exception:
        logger.exception("Could not stop dashboard news refresh.")
        return _json_response(
            {"error": "Could not stop automatic news refresh."},
            status=503,
        )
    return _json_response(status)


@app.get("/news")
def list_news():
    try:
        page, per_page = _parse_pagination()
        result = database.get_news_page(page=page, per_page=per_page)
    except ValueError as error:
        return _json_response({"error": str(error)}, status=400)
    except RuntimeError as error:
        return _database_error_response(error)

    return _json_response(result)


@app.get("/news/search")
def search_news():
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return _json_response(
            {"error": "keyword query parameter is required."},
            status=400,
        )
    if len(keyword) > 100:
        return _json_response(
            {"error": "keyword must be 100 characters or fewer."},
            status=400,
        )

    try:
        page, per_page = _parse_pagination()
        result = database.get_news_page(
            page=page,
            per_page=per_page,
            keyword=keyword,
        )
    except ValueError as error:
        return _json_response({"error": str(error)}, status=400)
    except RuntimeError as error:
        return _database_error_response(error)

    return _json_response(result)


@app.get("/news/category/<category>")
def news_by_category(category):
    matching_category = next(
        (
            known_category
            for known_category in VALID_CATEGORIES
            if known_category.casefold() == category.casefold()
        ),
        None,
    )
    if matching_category is None:
        return _json_response(
            {
                "error": "Invalid category.",
                "valid_categories": sorted(VALID_CATEGORIES),
            },
            status=400,
        )

    try:
        page, per_page = _parse_pagination()
        result = database.get_news_page(
            page=page,
            per_page=per_page,
            category=matching_category,
        )
    except ValueError as error:
        return _json_response({"error": str(error)}, status=400)
    except RuntimeError as error:
        return _database_error_response(error)

    return _json_response(result)


@app.get("/news/<article_id>")
def get_news(article_id):
    try:
        article = database.get_news_article(article_id)
    except RuntimeError as error:
        return _database_error_response(error)

    if article is None:
        return _json_response({"error": "Article not found."}, status=404)
    return _json_response(article)


def _get_briefing_for_date(date_value):
    try:
        _parse_date(date_value)
    except ValueError as error:
        return _json_response({"error": str(error)}, status=400)

    try:
        briefing = database.get_briefing_by_date(date_value)
    except RuntimeError as error:
        return _database_error_response(error)

    if briefing is None:
        return _json_response({"error": "Briefing not found."}, status=404)
    return _json_response(briefing)


@app.get("/briefings")
def list_briefings():
    date_value = request.args.get("date")
    if date_value is not None:
        return _get_briefing_for_date(date_value)

    try:
        page, per_page = _parse_pagination()
        result = database.get_briefings_page(page=page, per_page=per_page)
    except ValueError as error:
        return _json_response({"error": str(error)}, status=400)
    except RuntimeError as error:
        return _database_error_response(error)

    return _json_response(result)


@app.get("/briefings/<date_value>")
def briefing_by_date(date_value):
    return _get_briefing_for_date(date_value)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app.run(host="127.0.0.1", port=5000)
