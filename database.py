from pymongo import MongoClient
from datetime import date, datetime, time, timedelta, timezone
import re

from bson import ObjectId
from pymongo.errors import DuplicateKeyError, PyMongoError

from config import DATABASE_NAME, MONGODB_URI


client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=5000,
)
database = client[DATABASE_NAME]
news_collection = database["news"]
daily_briefings_collection = database["daily_briefings"]


def connect_to_mongodb():
    try:
        check_database_connection()
    except RuntimeError as error:
        raise ConnectionError(
            "Could not connect to MongoDB. Check that it is running and "
            "that MONGODB_URI is correct."
        ) from error

    try:
        news_collection.create_index("url", unique=True)
        daily_briefings_collection.create_index("briefing_date", unique=True)
    except PyMongoError as error:
        raise RuntimeError(
            "MongoDB index setup failed. Check for duplicate article URLs "
            "or briefing dates in existing data."
        ) from error

    return database


def check_database_connection():
    try:
        client.admin.command("ping")
    except PyMongoError as error:
        raise RuntimeError("MongoDB is unavailable.") from error


def save_news_articles(articles):
    if not isinstance(articles, list):
        raise TypeError("articles must be a list of article dictionaries.")

    if not articles:
        return {
            "inserted": 0,
            "duplicates": 0,
        }

    documents = []
    for article in articles:
        if not isinstance(article, dict):
            raise TypeError("Each article must be a dictionary.")

        url = article.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Each article must have a non-empty URL.")

        document = dict(article)
        document["url"] = url.strip()
        documents.append(document)

    connect_to_mongodb()

    inserted_count = 0
    duplicate_count = 0

    for document in documents:
        try:
            news_collection.insert_one(document)
            inserted_count += 1
        except DuplicateKeyError:
            duplicate_count += 1
        except PyMongoError as error:
            raise RuntimeError(
                "Could not save news in MongoDB. Check the database connection."
            ) from error

    return {
        "inserted": inserted_count,
        "duplicates": duplicate_count,
    }


def get_news_for_date(briefing_date):
    if not isinstance(briefing_date, date) or isinstance(briefing_date, datetime):
        raise TypeError("briefing_date must be a date.")

    start_of_day = datetime.combine(
        briefing_date,
        time.min,
        tzinfo=timezone.utc,
    )
    start_of_next_day = start_of_day + timedelta(days=1)
    date_range = {
        "$gte": start_of_day,
        "$lt": start_of_next_day,
    }
    query = {
        "$or": [
            {"published_at": date_range},
            {
                "published_at": None,
                "collected_at": date_range,
            },
        ]
    }

    try:
        connect_to_mongodb()
        return list(
            news_collection.find(query).sort("published_at", -1)
        )
    except (ConnectionError, RuntimeError, PyMongoError) as error:
        raise RuntimeError(
            "Could not retrieve news from MongoDB. Check the database connection."
        ) from error


def save_daily_briefing(briefing):
    if not isinstance(briefing, dict):
        raise TypeError("briefing must be a dictionary.")

    briefing_date = briefing.get("briefing_date")
    if not isinstance(briefing_date, str) or not briefing_date.strip():
        raise ValueError("briefing must have a non-empty briefing_date.")

    document = dict(briefing)
    document["briefing_date"] = briefing_date.strip()
    document.setdefault("created_at", datetime.now(timezone.utc))

    try:
        connect_to_mongodb()
        daily_briefings_collection.update_one(
            {"briefing_date": document["briefing_date"]},
            {
                "$set": {
                    key: value
                    for key, value in document.items()
                    if key != "created_at"
                },
                "$setOnInsert": {"created_at": document["created_at"]},
            },
            upsert=True,
        )
    except (ConnectionError, RuntimeError, PyMongoError) as error:
        raise RuntimeError(
            "Could not save the daily briefing. Check the database connection."
        ) from error

    return document


def _validate_page_arguments(page, per_page):
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError("page must be a positive integer.")
    if (
        not isinstance(per_page, int)
        or isinstance(per_page, bool)
        or not 1 <= per_page <= 100
    ):
        raise ValueError("per_page must be between 1 and 100.")


def get_news_page(page=1, per_page=20, category=None, keyword=None):
    _validate_page_arguments(page, per_page)

    query = {}
    if category:
        query["category"] = category
    if keyword:
        keyword_pattern = re.escape(keyword)
        query["$or"] = [
            {"title": {"$regex": keyword_pattern, "$options": "i"}},
            {"description": {"$regex": keyword_pattern, "$options": "i"}},
            {"category": {"$regex": keyword_pattern, "$options": "i"}},
        ]

    try:
        connect_to_mongodb()
        total = news_collection.count_documents(query)
        articles = list(
            news_collection.find(query)
            .sort("published_at", -1)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
    except (ConnectionError, RuntimeError, PyMongoError) as error:
        raise RuntimeError(
            "Could not retrieve news from MongoDB."
        ) from error

    return {
        "items": articles,
        "page": page,
        "per_page": per_page,
        "total": total,
    }


def get_news_article(article_id):
    if not ObjectId.is_valid(article_id):
        return None

    try:
        connect_to_mongodb()
        return news_collection.find_one({"_id": ObjectId(article_id)})
    except (ConnectionError, RuntimeError, PyMongoError) as error:
        raise RuntimeError(
            "Could not retrieve news from MongoDB."
        ) from error


def get_briefings_page(page=1, per_page=20):
    _validate_page_arguments(page, per_page)

    try:
        connect_to_mongodb()
        total = daily_briefings_collection.count_documents({})
        briefings = list(
            daily_briefings_collection.find({})
            .sort("briefing_date", -1)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
    except (ConnectionError, RuntimeError, PyMongoError) as error:
        raise RuntimeError(
            "Could not retrieve briefings from MongoDB."
        ) from error

    return {
        "items": briefings,
        "page": page,
        "per_page": per_page,
        "total": total,
    }


def get_briefing_by_date(briefing_date):
    if not isinstance(briefing_date, str):
        raise TypeError("briefing_date must be a string.")

    try:
        connect_to_mongodb()
        return daily_briefings_collection.find_one(
            {"briefing_date": briefing_date}
        )
    except (ConnectionError, RuntimeError, PyMongoError) as error:
        raise RuntimeError(
            "Could not retrieve briefings from MongoDB."
        ) from error
