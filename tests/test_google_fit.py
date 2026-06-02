import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from connectors import google_fit


class GoogleFitTest(unittest.TestCase):
    def test_date_bounds_use_berlin_calendar_day(self):
        start_ms, end_ms, start_ns, end_ns = google_fit._date_bounds(date(2026, 6, 2))

        expected_start = int(
            datetime(2026, 6, 2, tzinfo=ZoneInfo("Europe/Berlin")).timestamp() * 1000
        )
        expected_end = int(
            datetime(2026, 6, 3, tzinfo=ZoneInfo("Europe/Berlin")).timestamp() * 1000
        )

        self.assertEqual(start_ms, expected_start)
        self.assertEqual(end_ms, expected_end)
        self.assertEqual(start_ns, expected_start * 1_000_000)
        self.assertEqual(end_ns, expected_end * 1_000_000)

    def test_sum_steps_from_aggregate_response(self):
        response = {
            "bucket": [
                {
                    "dataset": [
                        {"point": [{"value": [{"intVal": 1200}]}]},
                        {"point": [{"value": [{"intVal": 3400}]}]},
                    ]
                }
            ]
        }

        self.assertEqual(google_fit._sum_steps_from_response(response), 4600)

    def test_sum_steps_from_estimated_steps_dataset(self):
        response = {
            "point": [
                {"value": [{"intVal": 1000}]},
                {"value": [{"intVal": 2500}]},
            ]
        }

        self.assertEqual(google_fit._sum_steps_from_dataset(response), 3500)


if __name__ == "__main__":
    unittest.main()
