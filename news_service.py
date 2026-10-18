from datetime import datetime, timezone

import requests

from config import GNEWS_API_KEY, GNEWS_API_URL, NEWS_QUERY
from models import categorize_news


class NewsAPIError(Exception):
    """Raised when the news provider cannot return usable articles."""


def _parse_published_date(value):
    if not value:
        return None

    try:
        published_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as error:
        raise NewsAPIError(
            "The news provider returned an invalid published date."
        ) from error

    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    return published_at.astimezone(timezone.utc)


def _normalize_article(article):
    if not isinstance(article, dict):
        return None

    title = article.get("title")
    url = article.get("url")
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(url, str) or not url.strip():
        return None

    description = article.get("description") or ""
    if not isinstance(description, str):
        description = ""

    source_data = article.get("source")
    source = source_data.get("name") if isinstance(source_data, dict) else None

    return {
        "title": title.strip(),
        "description": description.strip(),
        "source": source or "Unknown",
        "author": article.get("author"),
        "url": url.strip(),
        "category": categorize_news(title, description),
        "published_at": _parse_published_date(article.get("publishedAt")),
        "collected_at": datetime.now(timezone.utc),
    }


def fetch_latest_news():
    if not GNEWS_API_KEY:
        raise NewsAPIError(
            "GNEWS_API_KEY is missing. Add your GNews API key to .env."
        )

    try:
        response = requests.get(
            GNEWS_API_URL,
            params={
                "q": NEWS_QUERY,
                "lang": "en",
                "sortby": "publishedAt",
                "max": 10,
                "apikey": GNEWS_API_KEY,
            },
            timeout=15,
        )
    except requests.RequestException as error:
        raise NewsAPIError(
            "Could not reach the news provider. Check your network connection."
        ) from error

    if not response.ok:
        if response.status_code == 401:
            raise NewsAPIError(
                "GNews rejected the API key (HTTP 401). Check that "
                "GNEWS_API_KEY is an active key from your GNews account."
            )
        if response.status_code == 403:
            raise NewsAPIError(
                "GNews denied the request (HTTP 403). Its documentation "
                "associates this with a reached daily quota or an expired "
                "subscription. Check your GNews dashboard; the daily quota "
                "resets at 00:00 UTC."
            )
        if response.status_code == 429:
            raise NewsAPIError(
                "GNews rate limit reached (HTTP 429). Wait before retrying; "
                "the free plan allows one request per second."
            )
        raise NewsAPIError(
            f"The news provider returned HTTP status {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as error:
        raise NewsAPIError(
            "The news provider returned invalid JSON."
        ) from error

    if not isinstance(payload, dict):
        raise NewsAPIError("The news provider returned an unexpected response.")

    articles = payload.get("articles")
    if not isinstance(articles, list):
        raise NewsAPIError(
            "The GNews response has no article list or contains an API error."
        )

    normalized_articles = []
    for article in articles:
        normalized = _normalize_article(article)
        if normalized is not None:
            normalized_articles.append(normalized)

    return normalized_articles
