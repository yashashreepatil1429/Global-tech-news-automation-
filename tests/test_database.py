import unittest
from unittest.mock import patch

import database
from pymongo.errors import DuplicateKeyError, PyMongoError


class SaveNewsArticlesTests(unittest.TestCase):
    def test_empty_list_returns_zero_counts_without_connecting(self):
        with patch.object(database, "connect_to_mongodb") as connect:
            with patch.object(database.news_collection, "insert_one") as insert:
                result = database.save_news_articles([])

        self.assertEqual(result, {"inserted": 0, "duplicates": 0})
        connect.assert_not_called()
        insert.assert_not_called()

    def test_successful_and_duplicate_inserts_are_counted(self):
        articles = [
            {"title": "First story", "url": "https://example.test/first"},
            {"title": "Duplicate story", "url": "https://example.test/first"},
            {"title": "Second story", "url": "https://example.test/second"},
        ]

        with patch.object(database, "connect_to_mongodb") as connect:
            with patch.object(
                database.news_collection,
                "insert_one",
                side_effect=[object(), DuplicateKeyError("duplicate"), object()],
            ) as insert:
                result = database.save_news_articles(articles)

        self.assertEqual(result, {"inserted": 2, "duplicates": 1})
        self.assertEqual(insert.call_count, 3)
        connect.assert_called_once_with()
        self.assertNotIn("_id", articles[0])

    def test_missing_url_is_rejected_before_any_database_operation(self):
        articles = [
            {"title": "Valid story", "url": "https://example.test/valid"},
            {"title": "Missing URL"},
        ]

        with patch.object(database, "connect_to_mongodb") as connect:
            with patch.object(database.news_collection, "insert_one") as insert:
                with self.assertRaisesRegex(ValueError, "non-empty URL"):
                    database.save_news_articles(articles)

        connect.assert_not_called()
        insert.assert_not_called()

    def test_empty_url_is_rejected_before_any_database_operation(self):
        articles = [{"title": "Empty URL", "url": "   "}]

        with patch.object(database, "connect_to_mongodb") as connect:
            with patch.object(database.news_collection, "insert_one") as insert:
                with self.assertRaisesRegex(ValueError, "non-empty URL"):
                    database.save_news_articles(articles)

        connect.assert_not_called()
        insert.assert_not_called()

    def test_connection_failure_is_reported_without_inserting(self):
        with patch.object(
            database,
            "connect_to_mongodb",
            side_effect=ConnectionError("MongoDB unavailable"),
        ):
            with patch.object(database.news_collection, "insert_one") as insert:
                with self.assertRaisesRegex(ConnectionError, "MongoDB unavailable"):
                    database.save_news_articles(
                        [{"title": "Story", "url": "https://example.test/story"}]
                    )

        insert.assert_not_called()

    def test_insert_failure_raises_clear_error(self):
        article = {"title": "Story", "url": "https://example.test/story"}

        with patch.object(database, "connect_to_mongodb"):
            with patch.object(
                database.news_collection,
                "insert_one",
                side_effect=PyMongoError("private database details"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Could not save news"):
                    database.save_news_articles([article])

    def test_articles_must_be_a_list(self):
        with self.assertRaisesRegex(TypeError, "must be a list"):
            database.save_news_articles(None)

    def test_each_article_must_be_a_dictionary(self):
        with self.assertRaisesRegex(TypeError, "must be a dictionary"):
            database.save_news_articles(["not a dictionary"])


if __name__ == "__main__":
    unittest.main()
