import unittest
from types import SimpleNamespace

from config import Settings
from main import validate_bot_configuration


class MainConfigurationTest(unittest.TestCase):
    def test_reports_all_missing_required_settings(self):
        config = SimpleNamespace()

        with self.assertRaisesRegex(RuntimeError, "openai_api_key") as error:
            validate_bot_configuration(config)

        self.assertIn("telegram_bot_token", str(error.exception))
        self.assertIn("renpho_password", str(error.exception))

    def test_accepts_complete_configuration(self):
        config = SimpleNamespace(
            telegram_bot_token="token",
            telegram_chat_id=123,
            garmin_email="garmin@example.com",
            garmin_password="secret",
            renpho_email="renpho@example.com",
            renpho_password="secret",
            openai_api_key="sk-test",
        )

        validate_bot_configuration(config)

    def test_empty_chat_id_is_converted_to_none_for_clear_validation(self):
        settings = Settings(
            telegram_bot_token="token",
            telegram_chat_id="",
            garmin_email="garmin@example.com",
            garmin_password="secret",
            renpho_email="renpho@example.com",
            renpho_password="secret",
            openai_api_key="sk-test",
        )

        self.assertIsNone(settings.telegram_chat_id)
        with self.assertRaisesRegex(RuntimeError, "telegram_chat_id"):
            validate_bot_configuration(settings)
