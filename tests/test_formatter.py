import unittest

from analytics import formatter


class FormatterTest(unittest.TestCase):
    def test_gfit_auth_warning_escapes_markdown_detail(self):
        text = formatter.gfit_auth_warning(
            "Bitte google_fit_token.json mit GOOGLE_FIT_INTERACTIVE_AUTH=1 neu autorisieren."
        )

        self.assertIn("google\\_fit\\_token.json", text)
        self.assertIn("GOOGLE\\_FIT\\_INTERACTIVE\\_AUTH=1", text)

    def test_morning_uses_rehab_neutral_readiness_label_and_omits_missing_values(self):
        text = formatter.morning_briefing({
            "date": "2026-09-19",
            "knee_rehab_active": True,
            "readiness": {"score": 92, "recommendation": "Hart trainieren"},
            "sleep_duration_minutes": 480,
            "sleep_score": 90,
            "avg_hrv": 60,
            "hrv_status": "BALANCED",
            "body_battery": None,
            "resting_hr": None,
            "long_term_changes": {"vo2_max": {"value": 51.0, "previous": 49.5, "delta": 1.5}},
        }, coach_text="• ✅ Beispiel-Coach")
        self.assertIn("Hohe Reserve", text)
        self.assertNotIn("Hart trainieren", text)
        self.assertNotIn("None", text)
        self.assertIn("VO₂max", text)
        self.assertLess(text.index("Heute auffällig"), text.index("🧠"))

    def test_google_fit_source_does_not_claim_watch_was_not_worn(self):
        text = formatter.morning_briefing({
            "date": "2026-09-19",
            "readiness": {},
            "steps_source": "google_fit",
            "garmin_steps_raw": 0,
            "gfit_status": "ok",
        })
        self.assertIn("Schritte heute aus Google Fit", text)
        self.assertNotIn("nicht getragen", text)

    def test_morning_shows_both_step_sources_and_selected_value(self):
        text = formatter.morning_briefing({
            "date": "2026-09-19",
            "readiness": {},
            "steps": 10000,
            "steps_source": "google_fit",
            "garmin_steps_raw": 10000,
            "gfit_steps_raw": 10400,
        })
        self.assertIn("Garmin 10.000", text)
        self.assertIn("Handy 10.400", text)
        self.assertIn("verwendet: Handy", text)


if __name__ == "__main__":
    unittest.main()
