"""Personal planning choices live outside the public code and build context."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def profile_path() -> Path:
    local = ROOT / 'private/training/profile.json'
    default = local if local.exists() else Path(os.environ.get('DATA_DIR','/data'))/'training/profile.json'
    return Path(os.environ.get('TRAINING_PROFILE_PATH', str(default)))


def load_profile(*, required: bool = True) -> dict:
    try:
        return json.loads(profile_path().read_text(encoding='utf-8'))
    except FileNotFoundError:
        if required:
            raise ValueError('No local training profile configured; set TRAINING_PROFILE_PATH.') from None
        return {}
