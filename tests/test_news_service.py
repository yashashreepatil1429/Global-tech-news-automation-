import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import requests

import news_service


class FetchGNewsTests(unittest.TestCase):
    def setUp(self):
        self.article = {
            "title": "Quantum computing breakthrough",
            "description": "Researchers test a new qubit design.",
            "content": "Longer article content is not stored in this project.",
            "source": {
                "name": "Example Technology News",
                "url": "https://example.test",
            },
            "author": "A. Reporter",
            "publishedAt": "2026-10-18T06:30:00Z",
            "url": "https://example.test/quantum-story",
        }

    def _response(self, payload, ok=True, status_code=200):
        return SimpleNamespace(
            ok=ok,
            status_code=status_code,
            json=lambda: payload,
        )

    def test_requests_gnews_and_normalizes_articles(self):
        response = self._response(
            {
                "totalArticles": 1,
                "articles": [self.article, {"title": "Missing URL"}],
            }
        )

        with patch.object(news_service, "GNEWS_API_KEY", "test-key"):
            with patch.object(
                news_service.requests, "get", return_value=response
            ) as get:
                articles = news_service.fetch_latest_news()

        get.assert_called_once_with(
            "https://gnews.io/api/v4/search",
            params={
                "q": news_service.NEWS_QUERY,
                "lang": "en",
                "sortby": "publishedAt",
                "max": 10,
                "apikey": "test-key",
            },
            timeout=15,
        )
        self.assertEqual(len(articles), 1)
        self.assertEqual(
            articles[0]["source"],
            "Example Technology News",
        )
        self.assertEqual(articles[0]["author"], "A. Reporter")
        self.assertEqual(articles[0]["category"], "Quantum Computing")
        self.assertEqual(articles[0]["url"], self.article["url"])
        self.assertEqual(
            articles[0]["published_at"],
            datetime(2026, 10, 18, 6, 30, tzinfo=timezone.utc),
        )
        self.assertNotIn("content", articles[0])

    def test_empty_gnews_result_returns_empty_list(self):
        with patch.object(news_service, "GNEWS_API_KEY", "test-key"):
            with patch.object(
                news_service.requests,
                "get",
                return_value=self._response({"totalArticles": 0, "articles": []}),
            ):
                self.assertEqual(news_service.fetch_latest_news(), [])

    def test_missing_api_key_is_reported(self):
        with patch.object(news_service, "GNEWS_API_KEY", ""):
            with self.assertRaisesRegex(
                news_service.NewsAPIError, "GNEWS_API_KEY"
            ):
                news_service.fetch_latest_news()

    def test_network_and_http_errors_are_reported(self):
        with patch.object(news_service, "GNEWS_API_KEY", "test-key"):
            with patch.object(
                news_service.requests,
                "get",
                side_effect=requests.Timeout(),
            ):
                with self.assertRaisesRegex(
                    news_service.NewsAPIError, "network connection"
                ):
                    news_service.fetch_latest_news()

            with patch.object(
                news_service.requests,
                "get",
                return_value=self._response(
                    {"errors": ["Invalid API key"]},
                    ok=False,
                    status_code=403,
                ),
            ):
                with self.assertRaisesRegex(
                    news_service.NewsAPIError, "daily quota"
                ):
                    news_service.fetch_latest_news()

            for status_code, message in (
                (401, "active key"),
                (429, "Wait before retrying"),
            ):
                with self.subTest(status_code=status_code):
                    with patch.object(
                        news_service.requests,
                        "get",
                        return_value=self._response(
                            {"errors": ["provider details"]},
                            ok=False,
                            status_code=status_code,
                        ),
                    ):
                        with self.assertRaisesRegex(
                            news_service.NewsAPIError, message
                        ):
                            news_service.fetch_latest_news()

    def test_invalid_json_and_unexpected_response_are_reported(self):
        def invalid_json():
            raise ValueError("provider details")

        responses = [
            self._response(None),
            SimpleNamespace(ok=True, status_code=200, json=invalid_json),
            self._response({"errors": ["Invalid token"]}),
        ]

        with patch.object(news_service, "GNEWS_API_KEY", "test-key"):
            for response in responses:
                with self.subTest(response=response):
                    with patch.object(
                        news_service.requests,
                        "get",
                        return_value=response,
                    ):
                        with self.assertRaises(news_service.NewsAPIError):
                            news_service.fetch_latest_news()

    def test_invalid_publication_date_is_reported(self):
        invalid_article = dict(self.article, publishedAt="not-a-date")
        response = self._response({"articles": [invalid_article]})

        with patch.object(news_service, "GNEWS_API_KEY", "test-key"):
            with patch.object(
                news_service.requests, "get", return_value=response
            ):
                with self.assertRaisesRegex(
                    news_service.NewsAPIError, "invalid published date"
                ):
                    news_service.fetch_latest_news()


if __name__ == "__main__":
    unittest.main()
