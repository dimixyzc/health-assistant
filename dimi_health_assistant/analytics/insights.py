"""
Kombiniert Daten aus allen Quellen zu auswertbaren Snapshots.
"""
import logging
from datetime import date, timedelta
from typing import Optional

from connectors import garmin as garmin_conn
from connectors import renpho as renpho_conn
from connectors import google_fit as gfit_conn
from analytics import metrics
from analytics.deduplicator import merge_steps
from storage import database as db
from config import settings

logger = logging.getLogger(__name__)


async def get_daily_snapshot(for_date: Optional[str] = None) -> dict:
    target = for_date or date.today().isoformat()

    # Parallel fetchen
    import asyncio
    stats_task = asyncio.create_task(
        garmin_conn.get_today_stats(settings.garmin_email, settings.garmin_password, settings.data_dir)
    )
    sleep_task = asyncio.create_task(
        garmin_conn.get_sleep(settings.garmin_email, settings.garmin_password, settings.data_dir, target)
    )
    hrv_task = asyncio.create_task(
        garmin_conn.get_hrv_data(settings.garmin_email, settings.garmin_password, settings.data_dir, target)
    )
    readiness_task = asyncio.create_task(
        garmin_conn.get_training_readiness(settings.garmin_email, settings.garmin_password, settings.data_dir)
    )
    gfit_task = asyncio.create_task(
        gfit_conn.get_steps(settings.google_client_id, settings.google_client_secret, settings.data_dir)
    )

    stats, sleep, hrv, readiness, gfit_steps = await asyncio.gather(
        stats_task, sleep_task, hrv_task, readiness_task, gfit_task,
        return_exceptions=True,
    )

    # Fehler abfangen
    def safe(val, default=None):
        return default if isinstance(val, Exception) else val

    stats = safe(stats, {})
    sleep = safe(sleep, {})
    hrv = safe(hrv, {})
    readiness = safe(readiness, {})
    gfit_steps = safe(gfit_steps)

    steps, steps_source = merge_steps(stats.get("steps"), gfit_steps)

    snapshot = {
        "date": target,
        "steps": steps,
        "steps_source": steps_source,
        "calories": stats.get("calories"),
        "active_calories": stats.get("active_calories"),
        "active_minutes": stats.get("active_minutes"),
        "resting_hr": stats.get("resting_hr"),
        "avg_stress": stats.get("avg_stress"),
        "body_battery": stats.get("body_battery"),
        "sleep_duration_minutes": sleep.get("duration_minutes"),
        "sleep_score": sleep.get("sleep_score"),
        "deep_sleep_minutes": sleep.get("deep_sleep_minutes"),
        "rem_sleep_minutes": sleep.get("rem_sleep_minutes"),
        "avg_hrv": sleep.get("avg_hrv") or hrv.get("last_night"),
        "hrv_status": hrv.get("status"),
        "hrv_weekly_avg": hrv.get("weekly_avg"),
        "training_readiness_score": readiness.get("score"),
        "training_readiness_level": readiness.get("level"),
        "training_readiness_feedback": readiness.get("feedback"),
    }
    snapshot["readiness"] = metrics.calculate_readiness(
        snapshot,
        sleep_goal_minutes=settings.sleep_goal_minutes,
    )
    return snapshot


async def get_weekly_summary() -> dict:
    import asyncio
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    activities_task = asyncio.create_task(
        garmin_conn.get_weekly_activities(settings.garmin_email, settings.garmin_password, settings.data_dir)
    )
    snapshot_task = asyncio.create_task(get_daily_snapshot())
    weight_task = asyncio.create_task(get_weight_trend(days=30))

    # Schlafdaten für jeden Tag dieser Woche sammeln
    sleep_tasks = [
        asyncio.create_task(
            garmin_conn.get_sleep(
                settings.garmin_email, settings.garmin_password, settings.data_dir,
                (monday + timedelta(days=i)).isoformat()
            )
        )
        for i in range((today - monday).days + 1)
    ]

    activities, snapshot, weight_trend, *sleep_results = await asyncio.gather(
        activities_task, snapshot_task, weight_task, *sleep_tasks, return_exceptions=True
    )

    def safe(val, default):
        return default if isinstance(val, Exception) else val

    activities = safe(activities, [])
    snapshot = safe(snapshot, {})
    weight_trend = safe(weight_trend, {"available": False})
    sleep_days = [safe(s, {}) for s in sleep_results]

    activities = metrics.add_activity_loads(activities)
    gym_days = sum(1 for a in activities if _is_gym(a.get("type", "")))
    run_days = sum(1 for a in activities if _is_run(a.get("type", "")))
    total_distance = round(sum(a.get("distance_km") or 0 for a in activities), 1)
    total_duration = sum(a.get("duration_minutes") or 0 for a in activities)
    total_calories = sum(a.get("calories") or 0 for a in activities)
    total_load = round(sum(a.get("load") or 0 for a in activities), 1)
    training_trend = metrics.training_trend(activities)
    weekly_goals = metrics.weekly_goal_summary(
        gym_days,
        run_days,
        gym_goal=settings.weekly_gym_goal,
        run_goal=settings.weekly_run_goal,
    )

    # Schlaf-Durchschnitte
    sleep_durations = [s.get("duration_minutes") for s in sleep_days if s.get("duration_minutes")]
    sleep_scores = [s.get("sleep_score") for s in sleep_days if s.get("sleep_score")]
    deep_list = [s.get("deep_sleep_minutes") for s in sleep_days if s.get("deep_sleep_minutes")]
    rem_list = [s.get("rem_sleep_minutes") for s in sleep_days if s.get("rem_sleep_minutes")]

    def avg(lst):
        return round(sum(lst) / len(lst)) if lst else None

    return {
        "week_start": monday.isoformat(),
        "week_end": today.isoformat(),
        "total_activities": len(activities),
        "gym_days": gym_days,
        "run_days": run_days,
        "total_distance_km": total_distance,
        "total_duration_minutes": total_duration,
        "total_calories_burned": total_calories,
        "total_load": total_load,
        "training_trend": training_trend,
        **weekly_goals,
        "activities": activities,
        "avg_sleep_minutes": avg(sleep_durations),
        "avg_sleep_score": avg(sleep_scores),
        "avg_deep_sleep_minutes": avg(deep_list),
        "avg_rem_sleep_minutes": avg(rem_list),
        "today_hrv": snapshot.get("avg_hrv"),
        "today_body_battery": snapshot.get("body_battery"),
        "today_resting_hr": snapshot.get("resting_hr"),
        "snapshot": snapshot,
        # Renpho weight trend
        "weight_available": weight_trend.get("available", False),
        "latest_weight": weight_trend.get("latest_weight"),
        "weight_delta": weight_trend.get("weight_delta"),
        "latest_body_fat": weight_trend.get("latest_body_fat"),
        "fat_delta": weight_trend.get("fat_delta"),
        "latest_muscle_mass": weight_trend.get("latest_muscle_mass"),
        "muscle_delta": weight_trend.get("muscle_delta"),
        "latest_visceral_fat": weight_trend.get("latest_visceral_fat"),
        "latest_subfat": weight_trend.get("latest_subfat"),
        "latest_protein": weight_trend.get("latest_protein"),
        "latest_metabolic_age": weight_trend.get("latest_metabolic_age"),
        "weight_measurements": weight_trend.get("measurements_count"),
        "weight_latest_date": weight_trend.get("latest_date"),
    }


async def get_weight_trend(days: int = 30) -> dict:
    history = await db.get_renpho_history(settings.data_dir, days)

    if not history:
        return {"available": False}

    weights = [r["weight_kg"] for r in history if r.get("weight_kg")]
    fats = [r["body_fat_pct"] for r in history if r.get("body_fat_pct")]
    muscles = [r["muscle_mass_kg"] for r in history if r.get("muscle_mass_kg")]

    latest = history[-1]
    oldest = history[0]

    trend = {
        "available": True,
        "measurements_count": len(history),
        "latest_date": latest.get("date"),
        "latest_weight": latest.get("weight_kg"),
        "latest_body_fat": latest.get("body_fat_pct"),
        "latest_subfat": latest.get("subfat_pct"),
        "latest_muscle_mass": latest.get("muscle_mass_kg"),
        "latest_lean_mass": latest.get("lean_mass_kg"),
        "latest_fat_free_weight": latest.get("fat_free_weight_kg"),
        "latest_bmi": latest.get("bmi"),
        "latest_visceral_fat": latest.get("visceral_fat"),
        "latest_bone_mass": latest.get("bone_mass_kg"),
        "latest_body_water": latest.get("body_water_pct"),
        "latest_protein": latest.get("protein_pct"),
        "latest_bmr": latest.get("bmr_kcal"),
        "latest_metabolic_age": latest.get("metabolic_age"),
        "weight_delta": round(latest.get("weight_kg", 0) - oldest.get("weight_kg", 0), 2) if weights else None,
        "fat_delta": round(latest.get("body_fat_pct", 0) - oldest.get("body_fat_pct", 0), 2) if fats else None,
        "muscle_delta": round(latest.get("muscle_mass_kg", 0) - oldest.get("muscle_mass_kg", 0), 2) if muscles else None,
        "avg_weight": round(sum(weights) / len(weights), 2) if weights else None,
        "period_days": days,
    }
    trend.update(metrics.body_trend(history, days))
    return trend


async def get_training_plan() -> dict:
    """Erstellt den tagesaktuellen Plan aus Readiness und Wochenziel."""
    weekly = await get_weekly_summary()
    if isinstance(weekly, Exception):
        weekly = {}
    snapshot = weekly.get("snapshot") or {}

    readiness = metrics.calculate_readiness(
        snapshot,
        sleep_goal_minutes=settings.sleep_goal_minutes,
        recent_activities=weekly.get("activities") or [],
    )
    snapshot["readiness"] = readiness
    return {
        "snapshot": snapshot,
        "weekly": weekly,
        "readiness": readiness,
        "suggested_session": _suggest_session(readiness, weekly),
    }


async def is_renpho_overdue(threshold_days: int = 5) -> bool:
    days = await db.days_since_last_renpho(settings.data_dir)
    if days is None:
        return True
    return days >= threshold_days


async def refresh_renpho_cache() -> Optional[dict]:
    """Holt neue Renpho-Daten und speichert sie in der DB."""
    measurements = await renpho_conn.get_measurements_since(
        settings.renpho_email, settings.renpho_password, days=60
    )
    for m in measurements:
        await db.upsert_renpho(settings.data_dir, m)
    return await db.get_latest_renpho(settings.data_dir)


def _is_gym(activity_type: str) -> bool:
    gym_types = {"strength_training", "fitness_equipment", "gym", "indoor_cycling", "yoga", "pilates", "weight_training"}
    return any(t in (activity_type or "").lower() for t in gym_types)


def _is_run(activity_type: str) -> bool:
    run_types = {"running", "trail_running", "treadmill_running"}
    return any(t in (activity_type or "").lower() for t in run_types)


def _suggest_session(readiness: dict, weekly: dict) -> str:
    recommendation = readiness.get("recommendation")
    gym_remaining = weekly.get("gym_remaining", 0)
    run_remaining = weekly.get("run_remaining", 0)

    if recommendation == "Ruhetag":
        return "Ruhetag oder 20-30 min Spaziergang, Mobility, früh schlafen."
    if recommendation == "Locker bewegen":
        if run_remaining > 0:
            return "Lockerer Z2-Lauf 30-45 min, keine Intervalle."
        return "Mobility, Core oder lockeres Ganzkörpertraining ohne Muskelversagen."
    if gym_remaining >= run_remaining and gym_remaining > 0:
        return "Krafttraining fokussiert: Grundübungen, 2-3 harte Arbeitssätze, sauber stoppen."
    if run_remaining > 0:
        return "Lauftraining: je nach Gefühl Tempo-Block oder solider Z2-Dauerlauf."
    return "Freie Qualitätseinheit nach Lust, aber Gesamtlast im Blick behalten."
