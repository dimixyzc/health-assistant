"""
Kombiniert Daten aus allen Quellen zu auswertbaren Snapshots.
"""
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from collections import Counter

from connectors import garmin as garmin_conn
from connectors import renpho as renpho_conn
from connectors import google_fit as gfit_conn
from analytics import metrics
from analytics.deduplicator import merge_steps
from storage import database as db
from config import settings

logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("Europe/Berlin")


async def get_daily_snapshot(for_date: Optional[str] = None) -> dict:
    fetched_at = datetime.now(LOCAL_TZ)
    target = for_date or fetched_at.date().isoformat()

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
        gfit_conn.get_steps(
            settings.google_client_id,
            settings.google_client_secret,
            settings.data_dir,
            date.fromisoformat(target),
        )
    )

    stats, sleep, hrv, readiness, gfit_result = await asyncio.gather(
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
    gfit_result = safe(gfit_result, {"steps": None, "status": "error", "detail": "Exception beim Abruf"})

    gfit_steps = gfit_result.get("steps")
    gfit_status = gfit_result.get("status", "error")
    garmin_steps_raw = stats.get("steps")
    steps, steps_source = merge_steps(garmin_steps_raw, gfit_steps)

    snapshot = {
        "date": target,
        "fetched_at": fetched_at.isoformat(timespec="minutes"),
        "fetched_time": fetched_at.strftime("%H:%M"),
        "steps": steps,
        "steps_source": steps_source,
        "garmin_steps_raw": garmin_steps_raw,
        "gfit_steps_raw": gfit_steps,
        "gfit_status": gfit_status,
        "gfit_detail": gfit_result.get("detail"),
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


async def get_hrv_trend(days: int = 28) -> dict:
    """Holt eine kompakte HRV-Zeitreihe für Verlaufsfragen."""
    import asyncio

    end = datetime.now(LOCAL_TZ).date()
    start = end - timedelta(days=days - 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    semaphore = asyncio.Semaphore(4)

    async def fetch_day(day: str):
        async with semaphore:
            return await garmin_conn.get_hrv_data(
                settings.garmin_email, settings.garmin_password, settings.data_dir, day
            )

    tasks = [
        asyncio.create_task(fetch_day(day))
        for day in dates
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    samples = []
    for day, result in zip(dates, results):
        if isinstance(result, Exception):
            continue
        raw_value = result.get("last_night") or result.get("weekly_avg")
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if value.is_integer():
            value = int(value)
        samples.append({
            "date": day,
            "value": value,
            "status": result.get("status"),
            "weekly_avg": result.get("weekly_avg"),
        })

    values = [s["value"] for s in samples]
    if not values:
        return {
            "available": False,
            "period_days": days,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "samples": [],
        }

    first = values[0]
    latest = values[-1]
    midpoint = max(1, len(values) // 2)
    early_avg = round(sum(values[:midpoint]) / midpoint)
    late_avg = round(sum(values[midpoint:]) / max(1, len(values[midpoint:])))
    status_counts = {}
    for sample in samples:
        status = sample.get("status") or "UNKNOWN"
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "available": True,
        "period_days": days,
        "start_date": samples[0]["date"],
        "end_date": samples[-1]["date"],
        "samples_count": len(samples),
        "latest": latest,
        "first": first,
        "delta": round(latest - first),
        "average": round(sum(values) / len(values)),
        "minimum": min(values),
        "maximum": max(values),
        "early_avg": early_avg,
        "late_avg": late_avg,
        "trend_delta": round(late_avg - early_avg),
        "status_counts": status_counts,
        "samples": samples,
    }


async def get_weekly_summary() -> dict:
    import asyncio
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    activities_task = asyncio.create_task(
        garmin_conn.get_weekly_activities(settings.garmin_email, settings.garmin_password, settings.data_dir)
    )
    snapshot_task = asyncio.create_task(get_daily_snapshot())
    weight_task = asyncio.create_task(get_weight_trend(days=30))
    journal_task = asyncio.create_task(get_journal_review(days=7))

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

    activities, snapshot, weight_trend, journal_review, *sleep_results = await asyncio.gather(
        activities_task, snapshot_task, weight_task, journal_task, *sleep_tasks, return_exceptions=True
    )

    def safe(val, default):
        return default if isinstance(val, Exception) else val

    activities = safe(activities, [])
    snapshot = safe(snapshot, {})
    weight_trend = safe(weight_trend, {"available": False})
    journal_review = safe(journal_review, {"available": False})
    sleep_days = [safe(s, {}) for s in sleep_results]

    activities = metrics.add_activity_loads(activities)
    gym_days = sum(1 for a in activities if _is_gym(a.get("type", "")))
    cardio_days = sum(1 for a in activities if _is_cardio(a.get("type", "")))
    total_distance = round(sum(a.get("distance_km") or 0 for a in activities), 1)
    total_duration = sum(a.get("duration_minutes") or 0 for a in activities)
    total_calories = sum(a.get("calories") or 0 for a in activities)
    total_load = round(sum(a.get("load") or 0 for a in activities), 1)
    training_trend = metrics.training_trend(activities)
    weekly_goals = metrics.weekly_goal_summary(
        gym_days,
        cardio_days,
        gym_goal=settings.weekly_gym_goal,
        cardio_goal=settings.weekly_cardio_goal,
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
        "cardio_days": cardio_days,
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
        "journal": journal_review,
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


async def get_journal_review(days: int = 14) -> dict:
    entries = await db.get_journal_entries(settings.data_dir, days=days)
    experiments = await db.get_active_experiments(settings.data_dir)

    def avg(key: str) -> Optional[float]:
        values = [e.get(key) for e in entries if e.get(key) is not None]
        return round(sum(values) / len(values), 1) if values else None

    tag_counter: Counter[str] = Counter()
    symptom_counter: Counter[str] = Counter()
    for entry in entries:
        for raw_tag in (entry.get("tags") or "").split(","):
            tag = raw_tag.strip().lower()
            if tag:
                tag_counter[tag] += 1
        for raw_symptom in (entry.get("symptoms") or "").split(","):
            symptom = raw_symptom.strip().lower()
            if symptom:
                symptom_counter[symptom] += 1

    latest = entries[-1] if entries else None
    prior = entries[:-1]
    energy_values = [e.get("energy") for e in entries if e.get("energy") is not None]
    stress_values = [e.get("stress") for e in entries if e.get("stress") is not None]
    signals = []
    if energy_values and energy_values[-1] <= 4:
        signals.append("Energie heute niedrig")
    if stress_values and stress_values[-1] >= 7:
        signals.append("Stress heute hoch")
    if len(energy_values) >= 4 and sum(1 for v in energy_values[-4:] if v <= 4) >= 3:
        signals.append("Energie mehrfach niedrig in den letzten Einträgen")
    if len(stress_values) >= 4 and sum(1 for v in stress_values[-4:] if v >= 7) >= 3:
        signals.append("Stress mehrfach hoch in den letzten Einträgen")
    if latest and prior and latest.get("mood") is not None:
        prior_moods = [e.get("mood") for e in prior if e.get("mood") is not None]
        if prior_moods and latest["mood"] <= (sum(prior_moods) / len(prior_moods)) - 2:
            signals.append("Stimmung deutlich unter deinem Journal-Schnitt")

    return {
        "available": bool(entries),
        "period_days": days,
        "entries_count": len(entries),
        "coverage_pct": round((len(entries) / days) * 100),
        "averages": {
            "mood": avg("mood"),
            "energy": avg("energy"),
            "stress": avg("stress"),
            "sleep_quality": avg("sleep_quality"),
            "soreness": avg("soreness"),
        },
        "top_tags": tag_counter.most_common(5),
        "top_symptoms": symptom_counter.most_common(5),
        "latest": latest,
        "recent_entries": entries[-7:],
        "signals": signals,
        "active_experiments": experiments,
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
    gym_types = {"strength_training", "fitness_equipment", "gym", "yoga", "pilates", "weight_training"}
    return any(t in (activity_type or "").lower() for t in gym_types)


def _is_cardio(activity_type: str) -> bool:
    cardio_types = {"indoor_cycling", "spinning", "cycling", "elliptical", "cardio", "rowing", "swimming"}
    return any(t in (activity_type or "").lower() for t in cardio_types)


def _suggest_session(readiness: dict, weekly: dict) -> str:
    recommendation = readiness.get("recommendation")
    gym_remaining = weekly.get("gym_remaining", 0)
    cardio_remaining = weekly.get("cardio_remaining", 0)

    if recommendation == "Ruhetag":
        return "Ruhetag oder 20-30 min Spaziergang, Mobility, früh schlafen."
    if recommendation == "Locker bewegen":
        if cardio_remaining > 0:
            return "Spinning Z2 30-45 min oder Crosstrainer locker, keine Intervalle."
        return "Mobility, Core oder lockeres Ganzkörpertraining ohne Muskelversagen."
    if gym_remaining >= cardio_remaining and gym_remaining > 0:
        return "Krafttraining fokussiert: Grundübungen knie-sicher, 2-3 harte Arbeitssätze, sauber stoppen."
    if cardio_remaining > 0:
        return "Cardio: Spinning-Intervalle (z.B. 5×3min Z4) oder Crosstrainer-Tempo, alternativ Rudern/Schwimmen."
    return "Freie Qualitätseinheit (Kraft oder impact-armes Cardio), Gesamtlast im Blick behalten."
