import unittest
from datetime import date, timedelta

from analytics.metrics import activity_load, body_trend, calculate_readiness, training_trend, weekly_goal_summary
from analytics.insights import _long_term_changes
from connectors.garmin import _find_numeric


class MetricsTest(unittest.TestCase):

    def test_long_term_changes_only_reports_configured_thresholds(self):
        changes = _long_term_changes(
            {"vo2_max": 51.0, "fitness_age": 28, "endurance_score": 80, "training_status": "Productive"},
            {"vo2_max": 50.2, "fitness_age": 27, "endurance_score": 75, "training_status": "Maintaining"},
        )
        self.assertNotIn("vo2_max", changes)
        self.assertIn("fitness_age", changes)
        self.assertIn("endurance_score", changes)
        self.assertIn("training_status", changes)

    def test_garmin_metric_extraction_handles_nested_endpoint_payloads(self):
        payload = {"trainingStatus": {"vo2MaxValue": 51.2}, "nested": [{"fitnessAge": 28}]}
        self.assertEqual(_find_numeric(payload, ("vo2max", "vo2_max")), 51.2)
        self.assertEqual(_find_numeric(payload, ("fitness_age", "fitnessage")), 28.0)
    def test_activity_load_prefers_hr_zones(self):
        load = activity_load({
            "type": "running",
            "duration_minutes": 60,
            "hr_zones": [
                {"zone": 2, "pct": 50},
                {"zone": 4, "pct": 50},
            ],
        })

        self.assertEqual(load["load_source"], "hr_zones")
        self.assertEqual(load["load_label"], "sehr hoch")
        self.assertGreater(load["load"], 130)

    def test_readiness_recommends_recovery_when_sleep_hrv_and_battery_are_low(self):
        readiness = calculate_readiness({
            "sleep_duration_minutes": 300,
            "sleep_score": 45,
            "hrv_status": "POOR",
            "body_battery": 32,
            "avg_stress": 62,
            "training_readiness_score": 40,
        })

        self.assertLess(readiness["score"], 55)
        self.assertEqual(readiness["recommendation"], "Ruhetag")
        self.assertIn("Schlafschuld", readiness["limiting_factors"])

    def test_weekly_goal_summary_reports_remaining_units(self):
        summary = weekly_goal_summary(gym_days=2, cardio_days=1, gym_goal=3, cardio_goal=3)

        self.assertEqual(summary["gym_remaining"], 1)
        self.assertEqual(summary["cardio_remaining"], 2)
        self.assertEqual(summary["goal_status"], "offen")

    def test_training_trend_returns_form_from_activity_loads(self):
        today = date(2026, 5, 30)
        activities = [
            {"start_time": (today - timedelta(days=1)).isoformat(), "load": 120},
            {"start_time": (today - timedelta(days=7)).isoformat(), "load": 80},
            {"start_time": (today - timedelta(days=14)).isoformat(), "load": 60},
        ]

        trend = training_trend(activities, today=today)

        self.assertGreater(trend["fatigue"], trend["fitness"])
        self.assertLess(trend["form"], 0)

    def test_body_trend_calculates_weekly_delta_and_quality(self):
        today = date.today()
        history = [
            {"date": (today - timedelta(days=14)).isoformat(), "weight_kg": 82.0, "body_fat_pct": 18.0, "muscle_mass_kg": 38.0},
            {"date": (today - timedelta(days=7)).isoformat(), "weight_kg": 81.0, "body_fat_pct": 17.5, "muscle_mass_kg": 38.3},
            {"date": today.isoformat(), "weight_kg": 80.0, "body_fat_pct": 17.0, "muscle_mass_kg": 38.6},
        ]

        trend = body_trend(history, days=14)

        self.assertEqual(trend["weight_delta_per_week"], -1.0)
        self.assertEqual(trend["measurement_quality"], "ok")


if __name__ == "__main__":
    unittest.main()
