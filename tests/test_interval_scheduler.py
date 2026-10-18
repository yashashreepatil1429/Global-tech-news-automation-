import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import interval_scheduler
from news_service import NewsAPIError


class IntervalSchedulerTests(unittest.TestCase):
    def setUp(self):
        interval_scheduler.stop_interval_schedule()
        interval_scheduler._state.update(
            {
                "running": False,
                "interval": None,
                "last_run_at": None,
                "last_run_id": 0,
                "last_attempt_at": None,
                "run_in_progress": False,
                "last_success": None,
                "last_error": None,
            }
        )

    def tearDown(self):
        interval_scheduler.stop_interval_schedule()

    def test_start_adds_interval_job_with_immediate_run_and_no_overlap(self):
        fake_scheduler = Mock()
        fake_scheduler.running = True
        fake_scheduler.get_job.return_value = None

        with patch.object(
            interval_scheduler,
            "BackgroundScheduler",
            return_value=fake_scheduler,
        ) as scheduler_class:
            status = interval_scheduler.start_interval_schedule("5_minutes")

        scheduler_class.assert_called_once_with(
            timezone=ZoneInfo("Asia/Kolkata")
        )
        fake_scheduler.start.assert_called_once_with()
        job_call = fake_scheduler.add_job.call_args
        self.assertEqual(job_call.args[0], interval_scheduler._run_interval_workflow)
        self.assertEqual(job_call.kwargs["trigger"], "interval")
        self.assertEqual(job_call.kwargs["seconds"], 300)
        self.assertEqual(job_call.kwargs["max_instances"], 1)
        self.assertTrue(job_call.kwargs["coalesce"])
        self.assertIsInstance(job_call.kwargs["next_run_time"], datetime)
        self.assertTrue(status["running"])
        self.assertEqual(status["interval"], "5_minutes")

    def test_invalid_interval_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Choose one of"):
            interval_scheduler.start_interval_schedule("10_seconds")

    def test_stop_removes_job_and_stops_background_scheduler(self):
        fake_scheduler = Mock()
        fake_scheduler.running = True
        interval_scheduler._scheduler = fake_scheduler
        interval_scheduler._state["running"] = True
        interval_scheduler._state["interval"] = "1_minute"

        status = interval_scheduler.stop_interval_schedule()

        fake_scheduler.remove_job.assert_called_once_with(
            "dashboard_news_refresh"
        )
        fake_scheduler.shutdown.assert_called_once_with(wait=False)
        self.assertFalse(status["running"])
        self.assertIsNone(status["interval"])

    def test_successful_workflow_updates_status(self):
        workflow_result = {
            "fetched": 5,
            "inserted": 3,
            "duplicates": 2,
            "briefing": {"briefing_date": "2026-10-18"},
            "elapsed_seconds": 1.0,
        }

        with patch.object(
            interval_scheduler,
            "run_news_workflow",
            return_value=workflow_result,
        ):
            interval_scheduler._run_interval_workflow()

        status = interval_scheduler.get_interval_status()
        self.assertEqual(status["last_run_id"], 1)
        self.assertFalse(status["run_in_progress"])
        self.assertEqual(
            status["last_success"],
            {
                "fetched": 5,
                "inserted": 3,
                "duplicates": 2,
                "briefing_date": "2026-10-18",
            },
        )
        self.assertIsNone(status["last_error"])

    def test_failed_workflow_updates_status_and_propagates(self):
        with patch.object(
            interval_scheduler,
            "run_news_workflow",
            side_effect=RuntimeError("private connection detail"),
        ):
            with self.assertLogs(
                interval_scheduler.logger, level="ERROR"
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "private connection detail"
                ):
                    interval_scheduler._run_interval_workflow()

        status = interval_scheduler.get_interval_status()
        self.assertEqual(status["last_run_id"], 1)
        self.assertFalse(status["run_in_progress"])
        self.assertIn("internal error", status["last_error"])
        self.assertNotIn("private connection detail", status["last_error"])

    def test_provider_failure_message_is_available_to_dashboard(self):
        message = (
            "GNews denied the request (HTTP 403). Check provider quota."
        )
        with patch.object(
            interval_scheduler,
            "run_news_workflow",
            side_effect=NewsAPIError(message),
        ):
            with self.assertLogs(
                interval_scheduler.logger, level="ERROR"
            ):
                with self.assertRaisesRegex(NewsAPIError, "HTTP 403"):
                    interval_scheduler._run_interval_workflow()

        self.assertEqual(
            interval_scheduler.get_interval_status()["last_error"],
            message,
        )


if __name__ == "__main__":
    unittest.main()
