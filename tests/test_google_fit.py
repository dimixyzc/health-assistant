import unittest
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from connectors import google_fit


class _FakeExecute:
    def __init__(self, response=None, error=None):
        self.response = response or {}
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.response


class _FakeDatasetApi:
    def __init__(self, service):
        self.service = service

    def aggregate(self, userId, body):
        return _FakeExecute(self.service.aggregate_response, self.service.aggregate_error)


class _FakeDatasetsApi:
    def __init__(self, service):
        self.service = service

    def get(self, userId, dataSourceId, datasetId):
        return _FakeExecute(self.service.dataset_response, self.service.dataset_error)


class _FakeDataSourcesApi:
    def __init__(self, service):
        self.service = service

    def datasets(self):
        return _FakeDatasetsApi(self.service)


class _FakeUsersApi:
    def __init__(self, service):
        self.service = service

    def dataset(self):
        return _FakeDatasetApi(self.service)

    def dataSources(self):
        return _FakeDataSourcesApi(self.service)


class _FakeService:
    def __init__(
        self,
        aggregate_response=None,
        dataset_response=None,
        aggregate_error=None,
        dataset_error=None,
    ):
        self.aggregate_response = aggregate_response or {}
        self.dataset_response = dataset_response or {}
        self.aggregate_error = aggregate_error
        self.dataset_error = dataset_error

    def users(self):
        return _FakeUsersApi(self)


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

    def test_fetch_steps_keeps_aggregate_when_estimated_source_fails(self):
        service = _FakeService(
            aggregate_response={
                "bucket": [{"dataset": [{"point": [{"value": [{"intVal": 4600}]}]}]}]
            },
            dataset_error=RuntimeError("404 dataSourceId not found"),
        )

        with patch.object(google_fit, "_build_service", return_value=service):
            result = google_fit._fetch_steps("client", "secret", "/tmp", date(2026, 6, 2))

        self.assertEqual(result["steps"], 4600)
        self.assertEqual(result["status"], "ok")

    def test_fetch_steps_uses_estimated_when_aggregate_fails(self):
        service = _FakeService(
            aggregate_error=RuntimeError("aggregate failed"),
            dataset_response={"point": [{"value": [{"intVal": 3500}]}]},
        )

        with patch.object(google_fit, "_build_service", return_value=service):
            result = google_fit._fetch_steps("client", "secret", "/tmp", date(2026, 6, 2))

        self.assertEqual(result["steps"], 3500)
        self.assertEqual(result["status"], "ok")

    def test_fetch_steps_returns_auth_expired_when_service_raises_auth_error(self):
        def boom(*args, **kwargs):
            raise google_fit.GoogleFitAuthError("token revoked")

        with patch.object(google_fit, "_build_service", side_effect=boom):
            result = google_fit._fetch_steps("client", "secret", "/tmp", date(2026, 6, 2))

        self.assertIsNone(result["steps"])
        self.assertEqual(result["status"], "auth_expired")
        self.assertIn("token revoked", result["detail"])

    def test_fetch_steps_returns_no_data_when_both_sources_empty(self):
        service = _FakeService(
            aggregate_response={"bucket": [{"dataset": []}]},
            dataset_response={"point": []},
        )

        with patch.object(google_fit, "_build_service", return_value=service):
            result = google_fit._fetch_steps("client", "secret", "/tmp", date(2026, 6, 2))

        self.assertEqual(result["steps"], 0)
        self.assertEqual(result["status"], "no_data")

    def test_fetch_steps_returns_error_when_both_sources_fail(self):
        service = _FakeService(
            aggregate_error=RuntimeError("aggregate failed"),
            dataset_error=RuntimeError("dataset failed"),
        )

        with patch.object(google_fit, "_build_service", return_value=service):
            result = google_fit._fetch_steps("client", "secret", "/tmp", date(2026, 6, 2))

        self.assertIsNone(result["steps"])
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
