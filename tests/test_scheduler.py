import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import config
import scheduler


class ScheduleConfigurationTests(unittest.TestCase):
    def test_defaults_use_six_am_and_kolkata_timezone(self):
        hour, minute, timezone_name = config.get_schedule_settings({})

        self.assertEqual((hour, minute, timezone_name), (6, 0, "Asia/Kolkata"))

    def test_reads_custom_time_and_timezone(self):
        settings = {
            "NEWS_SCHEDULE_HOUR": "7",
            "NEWS_SCHEDULE_MINUTE": "45",
            "NEWS_SCHEDULE_TIMEZONE": "UTC",
        }

        self.assertEqual(
            config.get_schedule_settings(settings),
            (7, 45, "UTC"),
        )

    def test_rejects_invalid_hour_minute_and_timezone(self):
        invalid_settings = [
            {"NEWS_SCHEDULE_HOUR": "24"},
            {"NEWS_SCHEDULE_MINUTE": "60"},
            {"NEWS_SCHEDULE_TIMEZONE": "Not/A_Real_Zone"},
        ]

        for settings in invalid_settings:
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    config.get_schedule_settings(settings)


class SchedulerRegistrationTests(unittest.TestCase):
    @patch.object(scheduler, "BlockingScheduler")
    def test_creates_daily_non_overlapping_job_in_configured_timezone(
        self, scheduler_class
    ):
        with patch.object(scheduler.config, "NEWS_SCHEDULE_HOUR", 8):
            with patch.object(scheduler.config, "NEWS_SCHEDULE_MINUTE", 15):
                with patch.object(
                    scheduler.config,
                    "NEWS_SCHEDULE_TIMEZONE",
                    "Asia/Kolkata",
                ):
                    instance = scheduler_class.return_value
                    result = scheduler.create_scheduler()

        scheduler_class.assert_called_once_with(
            timezone=ZoneInfo("Asia/Kolkata")
        )
        instance.add_job.assert_called_once_with(
            scheduler.run_news_workflow,
            trigger="cron",
            hour=8,
            minute=15,
            timezone=ZoneInfo("Asia/Kolkata"),
            id="daily_global_tech_news",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        self.assertIs(result, instance)

    @patch.object(scheduler, "create_scheduler")
    def test_run_scheduler_starts_scheduler_without_waiting_for_job(
        self, create_scheduler
    ):
        scheduler.run_scheduler()

        create_scheduler.return_value.start.assert_called_once_with()


class NewsWorkflowTests(unittest.TestCase):
    @patch.object(scheduler, "perf_counter", side_effect=[10.0, 12.5])
    @patch.object(scheduler, "generate_daily_briefing")
    @patch.object(scheduler, "save_news_articles")
    @patch.object(scheduler, "fetch_latest_news")
    def test_runs_fetch_store_then_briefing_and_reports_counts(
        self,
        fetch_news,
        save_articles,
        generate_briefing,
        perf_counter,
    ):
        events = []
        articles = [{"url": "https://example.test/article"}]
        briefing = {"briefing_date": "2026-10-18"}
        fetch_news.side_effect = lambda: events.append("fetch") or articles
        save_articles.side_effect = (
            lambda saved: events.append(("save", saved))
            or {"inserted": 1, "duplicates": 0}
        )
        generate_briefing.side_effect = (
            lambda: events.append("briefing") or briefing
        )

        with self.assertLogs(scheduler.logger, level="INFO") as logs:
            result = scheduler.run_news_workflow()

        self.assertEqual(events, ["fetch", ("save", articles), "briefing"])
        self.assertEqual(result["fetched"], 1)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(result["briefing"], briefing)
        self.assertEqual(result["elapsed_seconds"], 2.5)
        self.assertIn("completed in 2.50 seconds", "\n".join(logs.output))
        fetch_news.assert_called_once_with()
        save_articles.assert_called_once_with(articles)
        generate_briefing.assert_called_once_with()

    @patch.object(scheduler, "perf_counter", side_effect=[1.0, 3.0])
    @patch.object(scheduler, "generate_daily_briefing")
    @patch.object(scheduler, "save_news_articles")
    @patch.object(scheduler, "fetch_latest_news")
    def test_fetch_failure_is_logged_and_stops_workflow(
        self,
        fetch_news,
        save_articles,
        generate_briefing,
        perf_counter,
    ):
        fetch_news.side_effect = RuntimeError("news API unavailable")

        with self.assertLogs(scheduler.logger, level="ERROR") as logs:
            with self.assertRaisesRegex(RuntimeError, "news API unavailable"):
                scheduler.run_news_workflow()

        save_articles.assert_not_called()
        generate_briefing.assert_not_called()
        self.assertIn("failed after 2.00 seconds", "\n".join(logs.output))

    @patch.object(scheduler, "perf_counter", side_effect=[1.0, 1.5])
    @patch.object(scheduler, "generate_daily_briefing")
    @patch.object(scheduler, "save_news_articles")
    @patch.object(scheduler, "fetch_latest_news")
    def test_database_failure_is_logged_and_propagated(
        self,
        fetch_news,
        save_articles,
        generate_briefing,
        perf_counter,
    ):
        fetch_news.return_value = [{"url": "https://example.test/article"}]
        save_articles.side_effect = RuntimeError("MongoDB unavailable")

        with self.assertLogs(scheduler.logger, level="ERROR") as logs:
            with self.assertRaisesRegex(RuntimeError, "MongoDB unavailable"):
                scheduler.run_news_workflow()

        generate_briefing.assert_not_called()
        self.assertIn("RuntimeError", "\n".join(logs.output))

    @patch.object(scheduler, "perf_counter", side_effect=[1.0, 2.0])
    @patch.object(scheduler, "generate_daily_briefing")
    @patch.object(scheduler, "save_news_articles")
    @patch.object(scheduler, "fetch_latest_news")
    def test_briefing_failure_is_logged_and_propagated(
        self,
        fetch_news,
        save_articles,
        generate_briefing,
        perf_counter,
    ):
        fetch_news.return_value = []
        save_articles.return_value = {"inserted": 0, "duplicates": 0}
        generate_briefing.side_effect = RuntimeError("briefing database unavailable")

        with self.assertLogs(scheduler.logger, level="ERROR") as logs:
            with self.assertRaisesRegex(
                RuntimeError, "briefing database unavailable"
            ):
                scheduler.run_news_workflow()

        self.assertIn("failed after 1.00 seconds", "\n".join(logs.output))

    @patch.object(scheduler, "perf_counter", side_effect=[1.0, 1.5])
    @patch.object(scheduler, "generate_daily_briefing")
    @patch.object(scheduler, "save_news_articles")
    @patch.object(scheduler, "fetch_latest_news")
    def test_non_list_collector_result_fails_before_storage(
        self,
        fetch_news,
        save_articles,
        generate_briefing,
        perf_counter,
    ):
        fetch_news.return_value = None

        with self.assertLogs(scheduler.logger, level="ERROR"):
            with self.assertRaisesRegex(TypeError, "must return a list"):
                scheduler.run_news_workflow()

        save_articles.assert_not_called()
        generate_briefing.assert_not_called()


if __name__ == "__main__":
    unittest.main()
