from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    telegram_chat_id: int

    garmin_email: str
    garmin_password: str

    renpho_email: str
    renpho_password: str

    google_client_id: str = ""
    google_client_secret: str = ""

    openai_api_key: str
    openai_model: str = "gpt-5.5"

    renpho_reminder_days: int = 5
    sleep_goal_minutes: int = 480
    weekly_gym_goal: int = 3
    weekly_run_goal: int = 3

    data_dir: str = "/data"


settings = Settings()
