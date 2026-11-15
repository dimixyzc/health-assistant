from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any


def _extract_heart_rate_trace(detail: dict[str, Any]) -> list[dict[str, float]]:
    descriptors = {item.get("key"): item.get("metricsIndex") for item in detail.get("metricDescriptors", [])}
    hr_index = descriptors.get("directHeartRate")
    time_index = descriptors.get("sumElapsedDuration")
    if hr_index is None:
        return []
    points: list[dict[str, float]] = []
    for item in detail.get("activityDetailMetrics", []):
        metrics = item.get("metrics") or []
        try:
            hr = float(metrics[hr_index])
            elapsed = float(metrics[time_index]) if time_index is not None else float(len(points))
        except (IndexError, TypeError, ValueError):
            continue
        if 25 <= hr <= 240:
            points.append({"elapsed_seconds": elapsed, "bpm": hr})
    # Keep a compact trace with about one point per 15 seconds, adequate for
    # broad trends and recovery while avoiding unnecessary high-resolution data.
    compact: list[dict[str, float]] = []
    last_bucket = -1
    for point in points:
        bucket = int(point["elapsed_seconds"] // 15)
        if bucket != last_bucket:
            compact.append(point)
            last_bucket = bucket
    return compact


def extract_vo2_estimates(payload: Any, inherited_date: str = "") -> list[dict[str, Any]]:
    """Keep only dated numeric VO2 fields from Garmin's nested max-metrics response."""
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        current_date = inherited_date
        for key, value in payload.items():
            if str(key).lower() in {"calendardate", "date", "startdate"} and isinstance(value, str):
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    current_date = value
        for key, value in payload.items():
            if "vo2" in str(key).lower() and isinstance(value, (int, float)) and not isinstance(value, bool):
                found.append({"date": current_date, "metric_name": str(key), "value": float(value)})
            else:
                found.extend(extract_vo2_estimates(value, current_date))
    elif isinstance(payload, list):
        for value in payload:
            found.extend(extract_vo2_estimates(value, inherited_date))
    return [item for item in found if item["date"]]


def extract_strength_sets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract work-set fields; Garmin's activity endpoint represents mass in grams."""
    result = []
    last_name = ""
    for item in payload.get("exerciseSets", []):
        set_type = str(item.get("setType", "unknown")).upper()
        if set_type == "REST":
            continue
        if item.get("repetitionCount") is None:
            continue
        exercises = item.get("exercises") or []
        names = [exercise for exercise in exercises if exercise.get("name") or exercise.get("category")]
        if names:
            best = max(names, key=lambda exercise: float(exercise.get("probability") or 0))
            last_name = str(best.get("name") or best.get("category"))
        else:
            best = {}
        category = str(best.get("category", ""))
        if not last_name:
            continue
        try:
            raw_weight = float(item.get("weight")) if item.get("weight") is not None else None
        except (TypeError, ValueError):
            raw_weight = None
        load_kg = raw_weight / 1000 if raw_weight is not None else None
        result.append({
            "exercise_name": last_name,
            "category": category,
            "reps": int(item["repetitionCount"]) if item.get("repetitionCount") is not None else None,
            "load_kg": round(load_kg, 2) if load_kg is not None else None,
            "set_type": set_type,
        })
    return result


class GarminReader:
    """Read-only client for python-garminconnect. No write methods are exposed."""
    def __init__(self, email: str, password: str, token_dir: str):
        if not email or not password:
            raise ValueError("Set GARMIN_EMAIL and GARMIN_PASSWORD in the shared local environment")
        self.email, self.password = email, password
        self.token_path = token_dir
        self.client = None

    def login(self) -> None:
        from pathlib import Path
        from connectors.garmin import get_client
        token_path = Path(self.token_path)
        if token_path.name != '.garminconnect':
            raise ValueError('Use the shared DATA_DIR/.garminconnect token directory')
        self.client = asyncio.run(get_client(self.email,self.password,str(token_path.parent)))

    def fetch_activities(self, start: date, end: date) -> list[dict[str, Any]]:
        raw_items = self.client.get_activities_by_date(start.isoformat(), end.isoformat()) or []
        result = []
        for item in raw_items:
            activity_id = item.get("activityId")
            if not activity_id:
                continue
            activity_type = str((item.get("activityType") or {}).get("typeKey", "unknown")).lower()
            if not any(marker in activity_type for marker in
                       ("strength", "cycling", "rowing", "elliptical", "cardio", "ski", "running", "walking")):
                continue
            detail = self.client.get_activity_details(str(activity_id))
            trace = _extract_heart_rate_trace(detail)
            strength_sets = []
            if "strength" in activity_type:
                try:
                    exercise_payload = self.client.get_activity_exercise_sets(str(activity_id))
                    strength_sets = extract_strength_sets(exercise_payload)
                except Exception:
                    strength_sets = []
            result.append({
                "activity_id": str(activity_id),
                "local_start": str(item.get("startTimeLocal") or ""),
                "activity_type": activity_type,
                "duration_seconds": int(item.get("duration") or 0),
                "average_hr": item.get("averageHR"),
                "max_hr": item.get("maxHR"),
                "distance_m": item.get("distance"),
                "hr_samples_json": __import__("json").dumps(trace, separators=(",", ":")),
                "strength_sets_json": __import__("json").dumps(strength_sets, separators=(",", ":")),
            })
        return result

    def fetch_vo2_estimates(self, start: date, end: date) -> list[dict[str, Any]]:
        return extract_vo2_estimates(self.client.get_max_metrics_range(start.isoformat(), end.isoformat()))


async def import_range(reader: GarminReader, start: date, end: date):
    return await asyncio.to_thread(reader.fetch_activities, start, end)
