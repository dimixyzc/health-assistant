import unittest
from unittest.mock import Mock, patch

from renpho import RenphoAPIError, RenphoAuthError
from renpho.constants import APP_VERSION, PLATFORM
from connectors import renpho


class RenphoTest(unittest.IsolatedAsyncioTestCase):
    def test_login_sends_protocol_headers_before_authentication(self):
        response = Mock()
        response.json.return_value = {"code": 106, "message": "User does not exist"}
        with patch("requests.Session.post", return_value=response) as post:
            with self.assertRaises(renpho.RenphoAuthenticationError):
                renpho._make_client("test@example.invalid", "synthetic-password")
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["appVersion"], APP_VERSION)
        self.assertEqual(headers["platform"], PLATFORM)
        self.assertNotIn("token", headers)
        self.assertNotIn("userId", headers)
        self.assertEqual(post.call_args.kwargs["timeout"], (5, 15))

    async def test_decryption_and_network_errors_are_not_bad_credentials(self):
        for function in (renpho.get_latest_measurement, renpho.get_measurements_since):
            for error in (RenphoAPIError("Login", -114, "private server response"),
                          TimeoutError("private server response")):
                with self.subTest(function=function.__name__, error=type(error).__name__):
                    with patch("renpho.RenphoClient.login", side_effect=error):
                        with self.assertLogs(renpho.logger, level="ERROR") as logs:
                            with self.assertRaises(renpho.RenphoFetchError) as caught:
                                await function("test@example.invalid", "synthetic-password")
                    self.assertNotIsInstance(caught.exception, renpho.RenphoAuthenticationError)
                    self.assertNotIn("private server response", str(caught.exception))
                    self.assertNotIn("private server response", str(logs.output))
                    self.assertNotIn("Traceback", str(logs.output))

    async def test_explicit_rejection_keeps_its_error_type(self):
        for function in (renpho.get_latest_measurement, renpho.get_measurements_since):
            with patch("renpho.RenphoClient.login", side_effect=RenphoAuthError("Login", 104, "private")):
                with self.assertRaises(renpho.RenphoAuthenticationError) as caught:
                    await function("test@example.invalid", "synthetic-password")
            self.assertNotIn("private", str(caught.exception))

    async def test_successful_measurements_are_parsed_and_filtered(self):
        from datetime import date
        client = Mock()
        client.get_all_measurements.return_value = [
            {"timeStamp": date.today().isoformat(), "weight": 70, "bodyfat": 20},
            {"timeStamp": "2000-01-01", "weight": 69},
        ]
        with patch.object(renpho, "_make_client", return_value=client):
            latest = await renpho.get_latest_measurement("test@example.invalid", "synthetic")
            recent = await renpho.get_measurements_since("test@example.invalid", "synthetic")
        self.assertEqual(latest["weight_kg"], 70)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["date"], date.today().isoformat())
