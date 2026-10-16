import unittest
from datetime import date, timedelta

from app.forecast_engine import build_scenarios


class ForecastRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 10, 13)
        self.rows = [
            {"observation_date": (self.day - timedelta(days=offset)).isoformat(),
             "signal_source": "visits", "observation_count": 30}
            for offset in range(15)
        ]

    def test_single_last_day_spike_does_not_become_planning_anchor(self):
        self.rows[0]["observation_count"] = 120
        forecast = build_scenarios(self.rows, self.day)
        self.assertEqual(forecast["latest_visits"], 120)
        self.assertEqual(forecast["planning_anchor_visits"], 30)
        self.assertEqual(forecast["observed_weekly_change_pct"], 0)
        expected = next(row for row in forecast["scenarios"] if row["scenario"] == "expected")
        self.assertEqual(expected["points"][7]["projected_visits"], 30)

    def test_missing_days_are_not_silently_counted_as_zero(self):
        rows = [row for row in self.rows if row["observation_date"] not in {
            (self.day - timedelta(days=1)).isoformat(),
            (self.day - timedelta(days=2)).isoformat(),
            (self.day - timedelta(days=3)).isoformat(),
        }]
        with self.assertRaisesRegex(ValueError, "five reported visit days"):
            build_scenarios(rows, self.day)


if __name__ == "__main__":
    unittest.main()
