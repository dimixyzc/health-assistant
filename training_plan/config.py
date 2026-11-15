from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


_CONFIG_KEYS = {
    "GARMIN_EMAIL", "GARMIN_PASSWORD", "GARMIN_TOKEN_DIR", "TRAINING_DATA_DIR", "TIMEZONE",
    "PLAN_START_DATE", "INITIAL_IMPORT_SINCE", "CARDIO_MINUTES", "SUNDAY_CARDIO_ENABLED", "MODE",
    "CARDIO_BASELINE_DATE", "DATA_DIR", "TRAINING_PROFILE_PATH",
}


def _load_dotenv(path: Path | None = None) -> None:
    """Load only this app's needed keys; never prints or logs values."""
    if path is None:
        path = Path(os.getenv("GARMIN_ENV_FILE", str(ROOT / ".env"))).expanduser()
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in _CONFIG_KEYS:
            os.environ.setdefault(key, value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    garmin_email: str
    garmin_password: str
    garmin_token_dir: Path
    data_dir: Path
    timezone: str
    start_date: date
    initial_import_since: date
    cardio_minutes: int
    sunday_cardio_enabled: bool
    cardio_baseline_date: date
    mode: str

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        mode = os.getenv("MODE", "DRY_RUN").upper()
        if mode != "DRY_RUN":
            raise ValueError("Only MODE=DRY_RUN is supported until the test upload is approved.")
        health_data = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).expanduser()
        data_dir = Path(os.getenv("TRAINING_DATA_DIR", str(health_data / "training"))).expanduser()
        return cls(
            garmin_email=os.getenv("GARMIN_EMAIL", ""),
            garmin_password=os.getenv("GARMIN_PASSWORD", ""),
            garmin_token_dir=Path(os.getenv("GARMIN_TOKEN_DIR", str(health_data / ".garminconnect"))).expanduser(),
            data_dir=data_dir,
            timezone=os.getenv("TIMEZONE", "Europe/Berlin"),
            start_date=date.fromisoformat(os.getenv("PLAN_START_DATE", "2026-10-01")),
            initial_import_since=date.fromisoformat(os.getenv("INITIAL_IMPORT_SINCE", "2026-08-01")),
            cardio_minutes=max(10, int(os.getenv("CARDIO_MINUTES", "30"))),
            sunday_cardio_enabled=os.getenv("SUNDAY_CARDIO_ENABLED", "true").lower() in {"1", "true", "yes"},
            cardio_baseline_date=date.fromisoformat(os.getenv("CARDIO_BASELINE_DATE", "2026-08-07")),
            mode=mode,
        )
