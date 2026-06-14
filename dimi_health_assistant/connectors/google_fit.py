"""
Google Fit Connector — nur für Schritte wenn Garmin nicht getragen wird.
Google Fit REST API (deprecated → Google Health Connect 2026, Migration notwendig).
OAuth2 Token wird in data_dir persistiert.
"""
import asyncio
import logging
import os
from datetime import datetime, date, time, timedelta
from typing import Optional, TypedDict
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/fitness.activity.read"]
_TOKEN_FILE = "google_fit_token.json"
_STEP_DATA_SOURCE = "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
_LOCAL_TZ = ZoneInfo("Europe/Berlin")


class GoogleFitAuthError(Exception):
    """Google Fit token is missing, expired, or revoked."""


class StepsResult(TypedDict):
    steps: Optional[int]
    status: str  # "ok" | "auth_expired" | "no_data" | "disabled" | "error"
    detail: Optional[str]


def _result(steps: Optional[int], status: str, detail: Optional[str] = None) -> StepsResult:
    return {"steps": steps, "status": status, "detail": detail}


def _token_path(data_dir: str) -> str:
    return os.path.join(data_dir, _TOKEN_FILE)


def _interactive_auth_enabled() -> bool:
    return os.getenv("GOOGLE_FIT_INTERACTIVE_AUTH", "").lower() in {"1", "true", "yes"}


def _build_service(client_id: str, client_secret: str, data_dir: str):
    from google.oauth2.credentials import Credentials
    from google.auth.exceptions import RefreshError
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    path = _token_path(data_dir)

    if os.path.exists(path):
        creds = Credentials.from_authorized_user_file(path, _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                try:
                    os.replace(path, f"{path}.invalid")
                except OSError:
                    pass
                raise GoogleFitAuthError(
                    "Google Fit OAuth-Token ist ungültig oder wurde widerrufen. "
                    "Bitte google_fit_token.json mit GOOGLE_FIT_INTERACTIVE_AUTH=1 neu autorisieren."
                ) from e
        else:
            if not _interactive_auth_enabled():
                raise GoogleFitAuthError(
                    "Google Fit OAuth-Token fehlt oder kann nicht aktualisiert werden. "
                    "Bitte google_fit_token.json mit GOOGLE_FIT_INTERACTIVE_AUTH=1 neu autorisieren."
                )
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, _SCOPES)
            # Läuft einmalig interaktiv beim ersten Start
            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent",
            )
        with open(path, "w") as f:
            f.write(creds.to_json())

    return build("fitness", "v1", credentials=creds, cache_discovery=False)


def _date_bounds(d: date) -> tuple[int, int, int, int]:
    """Liefert lokale Tagesgrenzen als Millisekunden und Nanosekunden."""
    start = datetime.combine(d, time.min, tzinfo=_LOCAL_TZ)
    end = start + timedelta(days=1)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    return start_ms, end_ms, start_ms * 1_000_000, end_ms * 1_000_000


def _sum_steps_from_response(response: dict) -> int:
    total = 0
    for bucket in response.get("bucket", []):
        for dataset in bucket.get("dataset", []):
            for point in dataset.get("point", []):
                for val in point.get("value", []):
                    total += val.get("intVal", 0)
    return total


def _sum_steps_from_dataset(response: dict) -> int:
    total = 0
    for point in response.get("point", []):
        for val in point.get("value", []):
            total += val.get("intVal", 0)
    return total


def _fetch_aggregate_steps(service, start_ms: int, end_ms: int) -> int:
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.step_count.delta"}],
        "bucketByTime": {
            "period": {
                "type": "day",
                "value": 1,
                "timeZoneId": "Europe/Berlin",
            }
        },
        "startTimeMillis": start_ms,
        "endTimeMillis": end_ms,
    }

    response = service.users().dataset().aggregate(userId="me", body=body).execute()
    return _sum_steps_from_response(response)


def _fetch_estimated_steps(service, start_ns: int, end_ns: int) -> int:
    dataset_id = f"{start_ns}-{end_ns}"
    response = service.users().dataSources().datasets().get(
        userId="me",
        dataSourceId=_STEP_DATA_SOURCE,
        datasetId=dataset_id,
    ).execute()
    return _sum_steps_from_dataset(response)


def _fetch_steps(client_id: str, client_secret: str, data_dir: str, target: date) -> StepsResult:
    try:
        service = _build_service(client_id, client_secret, data_dir)
    except GoogleFitAuthError as e:
        logger.warning(str(e))
        return _result(None, "auth_expired", str(e))
    except Exception as e:
        logger.warning("Google Fit Service konnte nicht aufgebaut werden: %s", e)
        return _result(None, "error", str(e))

    try:
        start_ms, end_ms, start_ns, end_ns = _date_bounds(target)

        aggregate_total = 0
        aggregate_failed = False
        try:
            aggregate_total = _fetch_aggregate_steps(service, start_ms, end_ms)
        except Exception as e:
            aggregate_failed = True
            logger.warning("Google Fit Aggregate-Schritte konnten nicht abgerufen werden: %s", e)

        estimated_total = 0
        estimated_failed = False
        try:
            estimated_total = _fetch_estimated_steps(service, start_ns, end_ns)
        except Exception as e:
            estimated_failed = True
            logger.info("Google Fit estimated_steps-Datenquelle nicht nutzbar: %s", e)

        total = max(aggregate_total, estimated_total)
        logger.info(
            "Google Fit Schritte %s: aggregate=%s estimated=%s selected=%s",
            target.isoformat(),
            aggregate_total,
            estimated_total,
            total,
        )
        if total > 0:
            return _result(total, "ok")
        if aggregate_failed and estimated_failed:
            return _result(None, "error", "Beide Google-Fit-Datenquellen sind fehlgeschlagen.")
        return _result(0, "no_data")
    except Exception as e:
        logger.warning("Google Fit Schritte konnten nicht abgerufen werden: %s", e)
        return _result(None, "error", str(e))


async def get_steps(
    client_id: str,
    client_secret: str,
    data_dir: str,
    for_date: Optional[date] = None,
) -> StepsResult:
    """Gibt {steps, status, detail} zurück. status ∈ {ok, auth_expired, no_data, disabled, error}."""
    if not client_id or not client_secret:
        return _result(None, "disabled", "Google-Fit-Credentials nicht konfiguriert.")
    target = for_date or date.today()
    return await asyncio.to_thread(_fetch_steps, client_id, client_secret, data_dir, target)
