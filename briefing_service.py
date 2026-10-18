from datetime import date, datetime, time, timezone
from numbers import Real

from database import get_news_for_date, save_daily_briefing
from models import CATEGORY_KEYWORDS


MAX_ARTICLES = 15
MAX_ARTICLES_PER_CATEGORY = 3
CATEGORY_ORDER = tuple(CATEGORY_KEYWORDS) + ("Other Technology",)


class BriefingError(Exception):
    """Raised when a daily briefing cannot be generated or saved."""


def _as_utc_datetime(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _article_date(article):
    published_at = _as_utc_datetime(article.get("published_at"))
    if published_at is not None:
        return published_at.date()

    collected_at = _as_utc_datetime(article.get("collected_at"))
    if collected_at is not None:
        return collected_at.date()

    return None


def _article_score(article):
    for field in ("importance_score", "score"):
        score = article.get(field)
        if isinstance(score, Real) and not isinstance(score, bool):
            return float(score)
    return 0.0


def _published_timestamp(article):
    published_at = _as_utc_datetime(article.get("published_at"))
    return published_at.timestamp() if published_at is not None else 0


def _category_rank(category):
    try:
        return CATEGORY_ORDER.index(category)
    except ValueError:
        return len(CATEGORY_ORDER)


def select_articles(articles, briefing_date, limit=MAX_ARTICLES):
    if not isinstance(briefing_date, date):
        raise TypeError("briefing_date must be a date.")
    if not isinstance(articles, list):
        raise TypeError("articles must be a list.")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer.")

    unique_articles = {}
    for article in articles:
        if not isinstance(article, dict):
            continue
        url = article.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        if _article_date(article) != briefing_date:
            continue

        normalized_url = url.strip()
        existing = unique_articles.get(normalized_url)
        if existing is None or _article_score(article) > _article_score(existing):
            unique_articles[normalized_url] = article

    sorted_articles = sorted(
        unique_articles.values(),
        key=lambda article: (
            -_article_score(article),
            _category_rank(article.get("category")),
            -_published_timestamp(article),
        ),
    )

    selected = []
    category_counts = {}
    for article in sorted_articles:
        category = article.get("category")
        count = category_counts.get(category, 0)
        if count >= MAX_ARTICLES_PER_CATEGORY:
            continue

        selected.append(article)
        category_counts[category] = count + 1
        if len(selected) >= limit:
            break

    return selected


def _short_summary(description):
    if not isinstance(description, str) or not description.strip():
        return "No description was provided by the source."

    summary = " ".join(description.split())
    if len(summary) > 280:
        summary = summary[:277].rsplit(" ", 1)[0] + "..."
    return summary


def _format_publication_time(article):
    published_at = _as_utc_datetime(article.get("published_at"))
    if published_at is None:
        return "Not provided"
    return published_at.strftime("%Y-%m-%d %H:%M UTC")


def _render_briefing(briefing_date, categories):
    lines = [
        "DAILY GLOBAL TECH BRIEFING",
        f"Date: {briefing_date.isoformat()}",
    ]

    if not categories:
        lines.append("")
        lines.append("No saved news articles were found for this date.")
        return "\n".join(lines)

    for category in CATEGORY_ORDER:
        articles = categories.get(category)
        if not articles:
            continue

        lines.extend(["", category.upper()])
        for article in articles:
            lines.extend(
                [
                    f"- {article.get('title', 'Untitled')}",
                    f"  Summary: {_short_summary(article.get('description'))}",
                    f"  Source URL: {article['url']}",
                    f"  Published: {_format_publication_time(article)}",
                ]
            )

    return "\n".join(lines)


def generate_daily_briefing(briefing_date=None):
    if briefing_date is None:
        briefing_date = datetime.now(timezone.utc).date()
    if not isinstance(briefing_date, date):
        raise TypeError("briefing_date must be a date.")

    try:
        saved_articles = get_news_for_date(briefing_date)
        selected_articles = select_articles(saved_articles, briefing_date)

        categories = {}
        for article in selected_articles:
            category = article.get("category")
            if category not in CATEGORY_ORDER:
                category = "Other Technology"
            categories.setdefault(category, []).append(article)

        generated_at = datetime.now(timezone.utc)
        briefing = {
            "briefing_date": briefing_date.isoformat(),
            "generated_at": generated_at,
            "total_news": len(selected_articles),
            "categories": {
                category: len(articles)
                for category, articles in categories.items()
            },
            "top_news": selected_articles,
            "text": _render_briefing(briefing_date, categories),
            "created_at": generated_at,
        }
        return save_daily_briefing(briefing)
    except RuntimeError as error:
        raise BriefingError(
            "Could not generate the daily briefing because a database "
            "operation failed."
        ) from error
