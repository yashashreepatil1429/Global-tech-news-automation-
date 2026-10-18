import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from bson import ObjectId

import api
import interval_scheduler


class NewsAPITests(unittest.TestCase):
    def setUp(self):
        self.client = api.app.test_client()

    @patch.object(api.database, "get_news_page")
    def test_list_news_returns_paged_results_and_serializes_mongo_values(
        self, get_news_page
    ):
        article_id = ObjectId()
        get_news_page.return_value = {
            "items": [
                {
                    "_id": article_id,
                    "title": "Cloud update",
                    "published_at": datetime(
                        2026, 10, 18, 6, tzinfo=timezone.utc
                    ),
                }
            ],
            "page": 2,
            "per_page": 10,
            "total": 11,
        }

        response = self.client.get("/news?page=2&per_page=10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["items"][0]["_id"], str(article_id))
        self.assertEqual(
            response.json["items"][0]["published_at"],
            "2026-10-18T06:00:00+00:00",
        )
        self.assertEqual(response.json["total"], 11)
        get_news_page.assert_called_once_with(page=2, per_page=10)

    @patch.object(api.database, "get_news_page")
    def test_empty_news_results_return_empty_list(self, get_news_page):
        get_news_page.return_value = {
            "items": [],
            "page": 1,
            "per_page": 20,
            "total": 0,
        }

        response = self.client.get("/news")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["items"], [])
        self.assertEqual(response.json["total"], 0)

    def test_invalid_pagination_returns_bad_request(self):
        for query in ("?page=zero", "?page=0", "?per_page=101"):
            with self.subTest(query=query):
                response = self.client.get(f"/news{query}")
                self.assertEqual(response.status_code, 400)

    @patch.object(api.database, "get_news_page")
    def test_valid_category_is_normalized_and_invalid_category_is_rejected(
        self, get_news_page
    ):
        get_news_page.return_value = {
            "items": [],
            "page": 1,
            "per_page": 20,
            "total": 0,
        }

        response = self.client.get("/news/category/quantum%20computing")
        self.assertEqual(response.status_code, 200)
        get_news_page.assert_called_once_with(
            page=1,
            per_page=20,
            category="Quantum Computing",
        )

        response = self.client.get("/news/category/not-a-category")
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid_categories", response.json)

    @patch.object(api.database, "get_news_page")
    def test_search_requires_keyword_and_uses_existing_database_query(
        self, get_news_page
    ):
        get_news_page.return_value = {
            "items": [],
            "page": 1,
            "per_page": 20,
            "total": 0,
        }

        self.assertEqual(self.client.get("/news/search").status_code, 400)
        response = self.client.get("/news/search?keyword=python")
        self.assertEqual(response.status_code, 200)
        get_news_page.assert_called_once_with(
            page=1,
            per_page=20,
            keyword="python",
        )

    @patch.object(api.database, "get_news_article")
    def test_article_endpoint_returns_found_article_or_404(self, get_article):
        article_id = ObjectId()
        get_article.return_value = {"_id": article_id, "title": "Found"}

        response = self.client.get(f"/news/{article_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["title"], "Found")

        get_article.return_value = None
        response = self.client.get(f"/news/{ObjectId()}")
        self.assertEqual(response.status_code, 404)

        response = self.client.get("/news/not-an-object-id")
        self.assertEqual(response.status_code, 404)

    @patch.object(api.database, "get_briefings_page")
    def test_briefing_list_returns_empty_results(self, get_briefings_page):
        get_briefings_page.return_value = {
            "items": [],
            "page": 1,
            "per_page": 20,
            "total": 0,
        }

        response = self.client.get("/briefings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["items"], [])

    @patch.object(api.database, "get_briefing_by_date")
    def test_briefing_can_be_retrieved_by_path_or_query_date(
        self, get_briefing
    ):
        get_briefing.return_value = {
            "briefing_date": "2026-10-18",
            "text": "DAILY GLOBAL TECH BRIEFING",
        }

        for path in (
            "/briefings/2026-10-18",
            "/briefings?date=2026-10-18",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["briefing_date"], "2026-10-18")

        get_briefing.assert_any_call("2026-10-18")

    @patch.object(api.database, "get_briefing_by_date")
    def test_invalid_and_missing_briefing_date(self, get_briefing):
        for path in (
            "/briefings/not-a-date",
            "/briefings/20261018",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 400)
        get_briefing.assert_not_called()

        get_briefing.return_value = None
        response = self.client.get("/briefings/2026-10-18")
        self.assertEqual(response.status_code, 404)

    @patch.object(api.database, "get_news_page", side_effect=RuntimeError("secret"))
    def test_database_failure_returns_sanitized_service_unavailable(
        self, get_news_page
    ):
        response = self.client.get("/news")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json["error"],
            "Database unavailable. Please try again later.",
        )
        self.assertNotIn("secret", response.get_data(as_text=True))

    @patch.object(api.database, "check_database_connection")
    def test_health_and_docs_endpoints(self, check_connection):
        dashboard_response = self.client.get("/")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn(
            b"Daily Global Tech News",
            dashboard_response.data,
        )
        self.assertIn(b"Quantum Computing", dashboard_response.data)

        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")

        check_connection.side_effect = RuntimeError("private connection details")
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private connection", response.get_data(as_text=True))

        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)
        paths = [endpoint["path"] for endpoint in response.json["endpoints"]]
        self.assertIn("/", paths)
        self.assertIn("/news?page=1&per_page=20", paths)
        self.assertIn("/briefings/<date>", paths)

    @patch.object(interval_scheduler, "get_interval_status")
    def test_automation_status_returns_scheduler_state(self, get_status):
        get_status.return_value = {
            "running": True,
            "interval": "1_minute",
            "interval_label": "Every 1 minute",
        }

        response = self.client.get("/automation")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["interval"], "1_minute")

    @patch.object(interval_scheduler, "start_interval_schedule")
    def test_automation_start_validates_and_starts_interval(self, start):
        start.return_value = {
            "running": True,
            "interval": "5_minutes",
        }

        response = self.client.post(
            "/automation",
            json={"interval": "5_minutes"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["running"])
        start.assert_called_once_with("5_minutes")

    def test_automation_start_rejects_invalid_request(self):
        missing = self.client.post("/automation", json={})
        invalid = self.client.post(
            "/automation",
            json={"interval": "10_seconds"},
        )
        malformed = self.client.post(
            "/automation",
            data="not-json",
            content_type="application/json",
        )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(malformed.status_code, 400)

    @patch.object(interval_scheduler, "stop_interval_schedule")
    def test_automation_stop_clears_schedule(self, stop):
        stop.return_value = {"running": False, "interval": None}

        response = self.client.delete("/automation")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["running"])
        stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
