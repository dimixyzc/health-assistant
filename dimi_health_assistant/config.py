from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    telegram_chat_id: int | None = None

    @field_validator("telegram_chat_id", mode="before")
    @classmethod
    def empty_telegram_chat_id_is_none(cls, value):
        return None if value is None or not str(value).strip() else value

    garmin_email: str
    garmin_password: str

    renpho_email: str
    renpho_password: str

    google_client_id: str = ""
    google_client_secret: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-terra"

    renpho_reminder_days: int = 5
    sleep_goal_minutes: int = 480
    weekly_gym_goal: int = 3
    weekly_cardio_goal: int = 3

    data_dir: str = "/data"


settings = Settings()
