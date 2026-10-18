import unittest
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import Mock, patch

import briefing_service
import database


BRIEFING_DATE = date(2026, 10, 18)


def make_article(
    url,
    title,
    category="AI",
    published_at=None,
    description="A source-provided description.",
    **extra,
):
    article = {
        "url": url,
        "title": title,
        "category": category,
        "description": description,
        "source": "Example News",
        "published_at": published_at
        or datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc),
    }
    article.update(extra)
    return article


class SelectArticlesTests(unittest.TestCase):
    def test_filters_by_date_and_ranks_by_score_then_category(self):
        articles = [
            make_article(
                "https://example.test/ai",
                "AI story",
                category="AI",
                importance_score=5,
            ),
            make_article(
                "https://example.test/agent",
                "Agent story",
                category="Agentic AI",
                importance_score=5,
            ),
            make_article(
                "https://example.test/older",
                "Previous day story",
                published_at=datetime(2026, 10, 17, 23, tzinfo=timezone.utc),
                score=100,
            ),
            make_article(
                "https://example.test/high-score",
                "Higher score story",
                category="Other Technology",
                score=8,
            ),
        ]

        selected = briefing_service.select_articles(articles, BRIEFING_DATE)

        self.assertEqual(
            [article["title"] for article in selected],
            ["Higher score story", "Agent story", "AI story"],
        )

    def test_duplicate_urls_keep_the_higher_scored_article(self):
        articles = [
            make_article(
                "https://example.test/story",
                "Lower score version",
                score=1,
            ),
            make_article(
                "https://example.test/story",
                "Higher score version",
                score=4,
            ),
        ]

        selected = briefing_service.select_articles(articles, BRIEFING_DATE)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["title"], "Higher score version")

    def test_missing_publication_date_uses_collection_date(self):
        article = make_article(
            "https://example.test/no-published-date",
            "Collected today",
            published_at=None,
        )
        article["published_at"] = None
        article["collected_at"] = datetime(
            2026, 10, 18, 7, tzinfo=timezone.utc
        )

        self.assertEqual(
            briefing_service.select_articles([article], BRIEFING_DATE),
            [article],
        )


class GenerateDailyBriefingTests(unittest.TestCase):
    def test_generates_grouped_briefing_from_saved_articles(self):
        articles = [
            make_article(
                "https://example.test/quantum",
                "Quantum research update",
                category="Quantum Computing",
                description="Researchers report a measured result.",
            ),
            make_article(
                "https://example.test/ai",
                "AI model update",
                description="A company describes a model update.",
            ),
        ]

        with patch.object(
            briefing_service, "get_news_for_date", return_value=articles
        ):
            with patch.object(
                briefing_service, "save_daily_briefing", side_effect=lambda briefing: briefing
            ) as save:
                result = briefing_service.generate_daily_briefing(BRIEFING_DATE)

        self.assertEqual(result["briefing_date"], "2026-10-18")
        self.assertEqual(result["total_news"], 2)
        self.assertEqual(result["categories"]["AI"], 1)
        self.assertEqual(result["categories"]["Quantum Computing"], 1)
        self.assertLess(
            result["text"].index("AI\n"),
            result["text"].index("QUANTUM COMPUTING"),
        )
        self.assertIn("A company describes a model update.", result["text"])
        self.assertIn("https://example.test/ai", result["text"])
        self.assertIn("2026-10-18 08:00 UTC", result["text"])
        save.assert_called_once()

    def test_empty_results_create_an_explicit_empty_briefing(self):
        with patch.object(
            briefing_service, "get_news_for_date", return_value=[]
        ):
            with patch.object(
                briefing_service, "save_daily_briefing", side_effect=lambda briefing: briefing
            ):
                result = briefing_service.generate_daily_briefing(BRIEFING_DATE)

        self.assertEqual(result["total_news"], 0)
        self.assertEqual(result["categories"], {})
        self.assertIn("No saved news articles", result["text"])

    def test_database_read_failure_is_reported_as_briefing_error(self):
        with patch.object(
            briefing_service,
            "get_news_for_date",
            side_effect=RuntimeError("internal database detail"),
        ):
            with self.assertRaisesRegex(
                briefing_service.BriefingError, "database operation failed"
            ) as error:
                briefing_service.generate_daily_briefing(BRIEFING_DATE)

        self.assertNotIn("internal database detail", str(error.exception))

    def test_database_write_failure_is_reported_as_briefing_error(self):
        with patch.object(briefing_service, "get_news_for_date", return_value=[]):
            with patch.object(
                briefing_service,
                "save_daily_briefing",
                side_effect=RuntimeError("internal database detail"),
            ):
                with self.assertRaisesRegex(
                    briefing_service.BriefingError, "database operation failed"
                ) as error:
                    briefing_service.generate_daily_briefing(BRIEFING_DATE)

        self.assertNotIn("internal database detail", str(error.exception))


class DatabaseBriefingHelpersTests(unittest.TestCase):
    def test_get_news_for_date_queries_publication_or_collection_date(self):
        articles = [{"title": "Saved story"}]
        cursor = Mock()
        cursor.sort.return_value = articles

        with patch.object(database, "connect_to_mongodb"):
            with patch.object(
                database.news_collection, "find", return_value=cursor
            ) as find:
                result = database.get_news_for_date(BRIEFING_DATE)

        start = datetime.combine(BRIEFING_DATE, time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        date_range = {"$gte": start, "$lt": end}
        find.assert_called_once_with(
            {
                "$or": [
                    {"published_at": date_range},
                    {"published_at": None, "collected_at": date_range},
                ]
            }
        )
        cursor.sort.assert_called_once_with("published_at", -1)
        self.assertEqual(result, articles)

    def test_get_news_for_date_reports_connection_failure(self):
        with patch.object(
            database, "connect_to_mongodb", side_effect=ConnectionError("private")
        ):
            with self.assertRaisesRegex(RuntimeError, "Could not retrieve news"):
                database.get_news_for_date(BRIEFING_DATE)

    def test_save_daily_briefing_upserts_and_sets_creation_time_only_once(self):
        briefing = {
            "briefing_date": "2026-10-18",
            "total_news": 1,
            "created_at": datetime(2026, 10, 18, tzinfo=timezone.utc),
        }

        with patch.object(database, "connect_to_mongodb"):
            with patch.object(
                database.daily_briefings_collection, "update_one"
            ) as update:
                saved = database.save_daily_briefing(briefing)

        update.assert_called_once_with(
            {"briefing_date": "2026-10-18"},
            {
                "$set": {
                    "briefing_date": "2026-10-18",
                    "total_news": 1,
                },
                "$setOnInsert": {
                    "created_at": datetime(2026, 10, 18, tzinfo=timezone.utc)
                },
            },
            upsert=True,
        )
        self.assertEqual(saved, briefing)

    def test_save_daily_briefing_reports_database_failure(self):
        briefing = {"briefing_date": "2026-10-18"}
        with patch.object(database, "connect_to_mongodb"):
            with patch.object(
                database.daily_briefings_collection,
                "update_one",
                side_effect=database.PyMongoError("private"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Could not save the daily briefing"):
                    database.save_daily_briefing(briefing)


if __name__ == "__main__":
    unittest.main()
