"""
Google Fit Connector — nur für Schritte wenn Garmin nicht getragen wird.
Google Fit REST API (deprecated → Google Health Connect 2026, Migration notwendig).
OAuth2 Token wird in data_dir persistiert.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, date, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/fitness.activity.read"]
_TOKEN_FILE = "google_fit_token.json"
_STEP_DATA_SOURCE = "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"


def _token_path(data_dir: str) -> str:
    return os.path.join(data_dir, _TOKEN_FILE)


def _build_service(client_id: str, client_secret: str, data_dir: str):
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    path = _token_path(data_dir)

    if os.path.exists(path):
        creds = Credentials.from_authorized_user_file(path, _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, _SCOPES)
            # Läuft einmalig interaktiv beim ersten Start
            creds = flow.run_local_server(port=0)
        with open(path, "w") as f:
            f.write(creds.to_json())

    return build("fitness", "v1", credentials=creds)


def _date_to_nanos(d: date) -> tuple[int, int]:
    """Liefert Start- und End-Nanosekunden für einen Tag."""
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    end = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
    return int(start.timestamp() * 1e9), int(end.timestamp() * 1e9)


def _fetch_steps(client_id: str, client_secret: str, data_dir: str, target: date) -> Optional[int]:
    try:
        service = _build_service(client_id, client_secret, data_dir)
        start_ns, end_ns = _date_to_nanos(target)

        body = {
            "aggregateBy": [{"dataTypeName": "com.google.step_count.delta"}],
            "bucketByTime": {"durationMillis": 86400000},
            "startTimeMillis": start_ns // 1_000_000,
            "endTimeMillis": end_ns // 1_000_000,
        }

        response = service.users().dataset().aggregate(userId="me", body=body).execute()
        buckets = response.get("bucket", [])
        total = 0
        for bucket in buckets:
            for dataset in bucket.get("dataset", []):
                for point in dataset.get("point", []):
                    for val in point.get("value", []):
                        total += val.get("intVal", 0)
        return total if total > 0 else None
    except Exception as e:
        logger.warning(f"Google Fit Schritte konnten nicht abgerufen werden: {e}")
        return None


async def get_steps(client_id: str, client_secret: str, data_dir: str, for_date: Optional[date] = None) -> Optional[int]:
    """Gibt Schrittzahl für einen Tag zurück, oder None bei Fehler."""
    if not client_id or not client_secret:
        return None
    target = for_date or date.today()
    return await asyncio.to_thread(_fetch_steps, client_id, client_secret, data_dir, target)
