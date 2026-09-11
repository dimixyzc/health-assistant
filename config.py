from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Optional: the legacy Telegram bot still uses these settings.  The
    # Codex/ChatGPT report runner does not need either value.
    telegram_bot_token: str = ""
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

    # Optional: only required by the legacy Telegram coaching client.  A
    # scheduled Codex task supplies the coaching response directly.
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"

    renpho_reminder_days: int = 5
    sleep_goal_minutes: int = 480
    # Activity is observed as context during knee rehabilitation, not judged
    # against fitness targets. Set KNEE_REHAB_ACTIVE=false after clearance.
    knee_rehab_active: bool = True
    weekly_gym_goal: int = 3
    weekly_cardio_goal: int = 3

    data_dir: str = "/data"


settings = Settings()
