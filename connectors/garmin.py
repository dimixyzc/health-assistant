import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Optional

from garminconnect import Garmin, GarminConnectAuthenticationError

logger = logging.getLogger(__name__)

_client: Optional[Garmin] = None


def _get_token_path(data_dir: str) -> str:
    return os.path.join(data_dir, ".garminconnect")


def _create_client(email: str, password: str, data_dir: str) -> Garmin:
    token_path = _get_token_path(data_dir)
    client = Garmin(email, password, is_cn=False, prompt_mfa=None)
    try:
        client.login(token_path)
    except Exception:
        logger.info("Kein gültiger Token, logge mit Credentials ein...")
        client.login()
        client.garth.dump(token_path)
    return client


async def get_client(email: str, password: str, data_dir: str) -> Garmin:
    global _client
    if _client is None:
        _client = await asyncio.to_thread(_create_client, email, password, data_dir)
    return _client


async def get_today_stats(email: str, password: str, data_dir: str) -> dict:
    client = await get_client(email, password, data_dir)
    today = date.today().isoformat()

    def _fetch():
        stats = client.get_stats(today)
        body_battery = client.get_body_battery(today, today)
        return stats, body_battery

    stats, body_battery = await asyncio.to_thread(_fetch)

    battery_value = None
    if body_battery and isinstance(body_battery, list) and len(body_battery) > 0:
        entries = body_battery[0].get("bodyBatteryValuesArray", [])
        if entries:
            battery_value = entries[-1][1] if len(entries[-1]) > 1 else None

    return {
        "date": today,
        "steps": stats.get("totalSteps", 0),
        "calories": stats.get("totalKilocalories", 0),
        "active_calories": stats.get("activeKilocalories", 0),
        "active_minutes": stats.get("highlyActiveSeconds", 0) // 60,
        "moderate_minutes": stats.get("moderateIntensityMinutes", 0),
        "vigorous_minutes": stats.get("vigorousIntensityMinutes", 0),
        "resting_hr": stats.get("restingHeartRate"),
        "avg_stress": stats.get("averageStressLevel"),
        "body_battery": battery_value,
    }


async def get_sleep(email: str, password: str, data_dir: str, for_date: Optional[str] = None) -> dict:
    client = await get_client(email, password, data_dir)
    target = for_date or date.today().isoformat()

    def _fetch():
        return client.get_sleep_data(target)

    data = await asyncio.to_thread(_fetch)
    daily = data.get("dailySleepDTO", {})

    deep = (daily.get("deepSleepSeconds") or 0) // 60
    light = (daily.get("lightSleepSeconds") or 0) // 60
    rem = (daily.get("remSleepSeconds") or 0) // 60
    awake = (daily.get("awakeSleepSeconds") or 0) // 60

    # Garmin liefert manchmal sleepTimeInSeconds=0 obwohl Phasen korrekt sind
    # → Fallback: Summe aus Phasen (ohne Wachzeit)
    reported = (daily.get("sleepTimeInSeconds") or 0) // 60
    duration = reported if reported > 0 else (deep + light + rem)

    return {
        "date": target,
        "duration_minutes": duration,
        "deep_sleep_minutes": deep,
        "light_sleep_minutes": light,
        "rem_sleep_minutes": rem,
        "awake_minutes": awake,
        "sleep_score": daily.get("sleepScores", {}).get("overall", {}).get("value"),
        "avg_hrv": data.get("avgOvernightHrv"),
        "avg_resting_hr": daily.get("averageHeartRate"),
        "respiration_avg": daily.get("averageRespirationValue"),
    }


async def get_hrv_data(email: str, password: str, data_dir: str, for_date: Optional[str] = None) -> dict:
    client = await get_client(email, password, data_dir)
    target = for_date or date.today().isoformat()

    def _fetch():
        return client.get_hrv_data(target)

    data = await asyncio.to_thread(_fetch)
    summary = data.get("hrvSummary", {}) if isinstance(data, dict) else {}

    return {
        "date": target,
        "weekly_avg": summary.get("weeklyAvg"),
        "last_night": summary.get("lastNight"),
        "last_5min_hrv": summary.get("lastNight5MinHigh"),
        "status": summary.get("status"),
    }


async def get_training_readiness(email: str, password: str, data_dir: str) -> dict:
    client = await get_client(email, password, data_dir)
    today = date.today().isoformat()

    def _fetch():
        return client.get_training_readiness(today)

    data = await asyncio.to_thread(_fetch)
    entry = data[0] if isinstance(data, list) and data else (data or {})

    return {
        "date": today,
        "score": entry.get("score"),
        "level": entry.get("level"),
        "feedback": entry.get("feedbackLong") or entry.get("feedback"),
    }


async def get_recent_activities(email: str, password: str, data_dir: str, limit: int = 10) -> list[dict]:
    client = await get_client(email, password, data_dir)

    def _fetch():
        return client.get_activities(0, limit)

    activities = await asyncio.to_thread(_fetch)
    result = []
    for a in activities:
        result.append({
            "activity_id": a.get("activityId"),
            "name": a.get("activityName"),
            "type": a.get("activityType", {}).get("typeKey", "unknown"),
            "start_time": a.get("startTimeLocal"),
            "duration_minutes": int((a.get("duration") or 0) // 60),
            "distance_km": round((a.get("distance") or 0) / 1000, 2),
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "calories": a.get("calories"),
            "avg_pace_min_km": _pace(a.get("averageSpeed")),
            # Running Dynamics
            "avg_spm": a.get("averageRunningCadenceInStepsPerMinute"),
            "max_spm": a.get("maxRunningCadenceInStepsPerMinute"),
            "elevation_gain_m": round(a.get("elevationGain") or 0),
            "avg_ground_contact_ms": a.get("avgGroundContactTime"),
            "avg_vertical_oscillation_cm": a.get("avgVerticalOscillation"),
            "avg_vertical_ratio_pct": a.get("avgVerticalRatio"),
            "avg_stride_length_m": a.get("avgStrideLength"),
            # Training Load
            "training_effect_aerobic": a.get("aerobicTrainingEffect"),
            "training_effect_anaerobic": a.get("anaerobicTrainingEffect"),
            "training_stress_score": a.get("trainingStressScore"),
        })
    return result


async def get_activity_hr_zones(email: str, password: str, data_dir: str, activity_id: int) -> list[dict]:
    """Holt HF-Zonen für eine Aktivität: [{zone, pct, secs}, ...]"""
    client = await get_client(email, password, data_dir)

    def _fetch():
        return client.get_activity_hr_in_timezones(activity_id)

    try:
        data = await asyncio.to_thread(_fetch)
        if not data:
            return []
        total_secs = sum(z.get("secsInZone", 0) for z in data)
        if total_secs == 0:
            return []
        return [
            {
                "zone": z.get("zoneNumber"),
                "secs": z.get("secsInZone", 0),
                "pct": round(z.get("secsInZone", 0) / total_secs * 100),
            }
            for z in sorted(data, key=lambda x: x.get("zoneNumber", 0))
        ]
    except Exception as e:
        logger.warning(f"HR-Zonen für {activity_id} nicht verfügbar: {e}")
        return []


async def get_recent_activities_with_zones(
    email: str, password: str, data_dir: str, limit: int = 5
) -> list[dict]:
    """Aktivitäten + HR-Zonen parallel laden."""
    activities = await get_recent_activities(email, password, data_dir, limit)
    zone_tasks = [
        asyncio.create_task(
            get_activity_hr_zones(email, password, data_dir, a["activity_id"])
        )
        for a in activities if a.get("activity_id")
    ]
    zones_list = await asyncio.gather(*zone_tasks, return_exceptions=True)
    for activity, zones in zip(activities, zones_list):
        activity["hr_zones"] = zones if not isinstance(zones, Exception) else []
    return activities


def _pace(speed_ms: Optional[float]) -> Optional[float]:
    if not speed_ms or speed_ms == 0:
        return None
    return round(1000 / speed_ms / 60, 2)


async def get_weekly_activities(email: str, password: str, data_dir: str) -> list[dict]:
    """Aktivitäten der laufenden Woche (Mo–heute)."""
    client = await get_client(email, password, data_dir)
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    def _fetch():
        return client.get_activities_by_date(monday.isoformat(), today.isoformat())

    activities = await asyncio.to_thread(_fetch)
    return [
        {
            "name": a.get("activityName"),
            "type": a.get("activityType", {}).get("typeKey", "unknown"),
            "start_time": a.get("startTimeLocal"),
            "duration_minutes": int((a.get("duration") or 0) // 60),
            "distance_km": round((a.get("distance") or 0) / 1000, 2),
            "avg_hr": a.get("averageHR"),
            "calories": a.get("calories"),
            "avg_spm": a.get("averageRunningCadenceInStepsPerMinute"),
            "avg_pace_min_km": _pace(a.get("averageSpeed")),
            "elevation_gain_m": round(a.get("elevationGain") or 0),
        }
        for a in (activities or [])
    ]
