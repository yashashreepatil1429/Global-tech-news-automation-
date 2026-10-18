import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "tech_news")
GNEWS_API_URL = os.getenv(
    "GNEWS_API_URL",
    "https://gnews.io/api/v4/search",
)
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "")
NEWS_QUERY = os.getenv(
    "NEWS_QUERY",
    "technology OR artificial intelligence OR cybersecurity OR quantum computing",
)


def _get_schedule_value(name, value, default, minimum, maximum):
    if value is None:
        value = str(default)

    try:
        number = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a whole number.") from error

    if not minimum <= number <= maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}."
        )

    return number


def get_schedule_settings(environ=None):
    settings = os.environ if environ is None else environ
    hour = _get_schedule_value(
        "NEWS_SCHEDULE_HOUR",
        settings.get("NEWS_SCHEDULE_HOUR"),
        default=6,
        minimum=0,
        maximum=23,
    )
    minute = _get_schedule_value(
        "NEWS_SCHEDULE_MINUTE",
        settings.get("NEWS_SCHEDULE_MINUTE"),
        default=0,
        minimum=0,
        maximum=59,
    )
    timezone_name = settings.get("NEWS_SCHEDULE_TIMEZONE", "Asia/Kolkata")

    try:
        ZoneInfo(timezone_name)
    except (TypeError, ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError(
            "NEWS_SCHEDULE_TIMEZONE must be a valid IANA timezone name."
        ) from error

    return hour, minute, timezone_name


(
    NEWS_SCHEDULE_HOUR,
    NEWS_SCHEDULE_MINUTE,
    NEWS_SCHEDULE_TIMEZONE,
) = get_schedule_settings()
