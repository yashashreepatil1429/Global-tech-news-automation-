import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import database
import news_service
import scheduler
from bson import ObjectId
from pymongo.errors import DuplicateKeyError


class _SortedCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, field, direction):
        reverse = direction < 0
        self.documents.sort(
            key=lambda document: document.get(field) or datetime.min.replace(
                tzinfo=timezone.utc
            ),
            reverse=reverse,
        )
        return self

    def __iter__(self):
        return iter(self.documents)


class CompleteWorkflowIntegrationTests(unittest.TestCase):
    def test_gnews_fetch_storage_and_briefing_work_as_one_flow(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        gnews_payload = {
            "totalArticles": 2,
            "articles": [
                {
                    "title": (
                        "Artificial intelligence model release expands "
                        "developer access"
                    ),
                    "description": "The company announced a new model.",
                    "source": {"name": "Example Technology News"},
                    "author": "Technology Reporter",
                    "publishedAt": now.isoformat().replace("+00:00", "Z"),
                    "url": "https://example.test/ai-release",
                },
                {
                    "title": "Quantum computing research update",
                    "description": "Researchers describe a quantum advance.",
                    "source": {"name": "Example Science News"},
                    "author": None,
                    "publishedAt": now.isoformat().replace("+00:00", "Z"),
                    "url": "https://example.test/quantum-research",
                },
            ],
        }
        response = SimpleNamespace(
            ok=True,
            status_code=200,
            json=lambda: gnews_payload,
        )
        saved_articles = {}
        saved_briefings = {}

        def insert_one(document):
            if document["url"] in saved_articles:
                raise DuplicateKeyError("duplicate URL")
            stored_document = dict(document)
            stored_document["_id"] = ObjectId()
            saved_articles[document["url"]] = stored_document

        def find_articles(query):
            date_filter = query["$or"][0]["published_at"]
            start = date_filter["$gte"]
            end = date_filter["$lt"]
            matching = [
                document
                for document in saved_articles.values()
                if start <= document["published_at"] < end
            ]
            return _SortedCursor(matching)

        def update_briefing(query, update, upsert):
            briefing = dict(update["$set"])
            briefing.setdefault(
                "created_at",
                update["$setOnInsert"]["created_at"],
            )
            saved_briefings[query["briefing_date"]] = briefing

        with patch.object(database, "connect_to_mongodb"):
            with patch.object(
                news_service, "GNEWS_API_KEY", "test-key"
            ), patch.object(
                news_service.requests, "get", return_value=response
            ) as get_request:
                with patch.object(
                    database.news_collection,
                    "insert_one",
                    side_effect=insert_one,
                ):
                    with patch.object(
                        database.news_collection,
                        "find",
                        side_effect=find_articles,
                    ):
                        with patch.object(
                            database.daily_briefings_collection,
                            "update_one",
                            side_effect=update_briefing,
                        ):
                            result = scheduler.run_news_workflow()

        self.assertEqual(result["fetched"], 2)
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(result["briefing"]["total_news"], 2)
        self.assertIn(
            "Artificial intelligence model release",
            result["briefing"]["text"],
        )
        self.assertIn(
            "QUANTUM COMPUTING",
            result["briefing"]["text"],
        )
        self.assertEqual(len(saved_articles), 2)
        self.assertIn(result["briefing"]["briefing_date"], saved_briefings)
        self.assertEqual(get_request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
