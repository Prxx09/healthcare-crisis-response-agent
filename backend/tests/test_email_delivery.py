import asyncio
import threading
import time
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.email_alerts import _build_email, _build_no_alert_email, _send_smtp_sequentially, send_task_owner_notifications


class SequentialEmailDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_workflows_share_one_smtp_slot(self):
        active = 0
        maximum_active = 0
        counter_lock = threading.Lock()

        def fake_send(*_args):
            nonlocal active, maximum_active
            with counter_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.02)
            with counter_lock:
                active -= 1
            return "<test-message@example.com>"

        with patch("app.email_alerts._send_smtp", side_effect=fake_send):
            results = await asyncio.gather(*(
                _send_smtp_sequentially(None, ["recipient@example.com"], [], "test", "text", "<p>test</p>")
                for _ in range(3)
            ))

        self.assertEqual(maximum_active, 1)
        self.assertEqual(len(results), 3)

    async def test_task_email_omits_loopback_url(self):
        repository = SimpleNamespace(
            get_email_alert_config=AsyncMock(return_value={
                "owner_emails": {"Operations lead": "owner@example.com"},
                "timezone": "UTC",
            }),
            create_task_owner_notification=AsyncMock(),
        )
        settings = SimpleNamespace(public_app_url="http://127.0.0.1:5174")
        alert = {
            "id": 42,
            "hospitals": {"name": "North Hospital"},
            "conditions": {"name": "Dengue"},
        }
        action = {
            "id": 7,
            "owner_role": "Operations lead",
            "action_text": "Test supplies",
            "timeframe": "Within 4 hours",
        }
        with patch("app.email_alerts._send_smtp_sequentially", new_callable=AsyncMock) as send:
            send.return_value = "<test@example.com>"
            result = await send_task_owner_notifications(repository, settings, alert, [action])

        self.assertEqual(result, {"sent": 1, "failed": 0, "skipped": 0})
        text_body, html_body = send.await_args.args[-2:]
        expected_url = "http://127.0.0.1:5174/action-tracker"
        self.assertNotIn(expected_url, text_body)
        self.assertNotIn(expected_url, html_body)
        self.assertIn("Open CrisisWatch on the configured workstation", text_body)
        self.assertNotIn("href=", html_body)

    def test_report_templates_omit_loopback_url(self):
        settings = SimpleNamespace(public_app_url="http://127.0.0.1:5174")
        alert = {
            "id": 42,
            "alert_level": "escalate",
            "hospitals": {"name": "North Hospital"},
            "conditions": {"name": "Dengue"},
            "evidence_summary": {"supporting_sources": ["visits"], "signals": []},
        }
        for template in (
            _build_email([alert], date(2026, 10, 19), settings),
            _build_no_alert_email(date(2026, 10, 19), settings),
        ):
            self.assertNotIn("http://127.0.0.1:5174/", template[1])
            self.assertNotIn("http://127.0.0.1:5174/", template[2])
            self.assertNotIn("href=", template[2])

    def test_report_templates_link_reachable_https_frontend(self):
        settings = SimpleNamespace(public_app_url="https://crisiswatch.example.com")
        _, text_body, html_body = _build_no_alert_email(date(2026, 10, 19), settings)
        self.assertIn("https://crisiswatch.example.com/command-dashboard", text_body)
        self.assertIn('href="https://crisiswatch.example.com/command-dashboard"', html_body)


if __name__ == "__main__":
    unittest.main()
