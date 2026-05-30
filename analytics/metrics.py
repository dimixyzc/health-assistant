"""
Deterministische Health- und Trainingsmetriken.

Die Werte sind als Coaching-Signale gedacht, nicht als medizinische Diagnose.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from math import exp
from typing import Optional


@dataclass(frozen=True)
class ComponentScore:
    name: str
    score: int
    status: str
    reason: str


@dataclass(frozen=True)
class Readiness:
    score: int
    status: str
    recommendation: str
    intensity: str
    components: list[ComponentScore]
    limiting_factors: list[str]
    sleep_debt_minutes: int
    calibration: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["components"] = [asdict(c) for c in self.components]
        return data


_SPORT_WEIGHTS = {
    "running": 1.15,
    "trail_running": 1.25,
    "treadmill_running": 1.1,
    "cycling": 1.0,
    "indoor_cycling": 0.95,
    "strength_training": 0.9,
    "weight_training": 0.9,
    "fitness_equipment": 0.85,
    "walking": 0.55,
    "hiking": 0.85,
}

_ZONE_WEIGHTS = {1: 0.6, 2: 1.0, 3: 1.8, 4: 3.0, 5: 5.0}


def clamp(value: float, low: int = 0, high: int = 100) -> int:
    return int(max(low, min(high, round(value))))


def score_status(score: Optional[int]) -> str:
    if score is None:
        return "k.A."
    if score >= 85:
        return "Optimal"
    if score >= 70:
        return "Gut"
    if score >= 55:
        return "Vorsicht"
    return "Erholung"


def activity_load(activity: dict) -> dict:
    """Berechnet eine sportartübergreifende Belastung aus Zonen oder Fallbacks."""
    minutes = _num(activity.get("duration_minutes")) or 0
    sport = (activity.get("type") or "").lower()
    sport_weight = next((w for key, w in _SPORT_WEIGHTS.items() if key in sport), 1.0)

    zone_load = _zone_load(activity.get("hr_zones") or [], minutes)
    if zone_load is not None:
        load = zone_load * sport_weight
        source = "hr_zones"
    else:
        load, source = _fallback_activity_load(activity, minutes, sport_weight)

    load = round(load, 1)
    return {
        "load": load,
        "load_source": source,
        "load_label": load_label(load),
    }


def add_activity_loads(activities: list[dict]) -> list[dict]:
    result = []
    for activity in activities:
        enriched = dict(activity)
        enriched.update(activity_load(activity))
        result.append(enriched)
    return result


def load_label(load: float) -> str:
    if load >= 130:
        return "sehr hoch"
    if load >= 75:
        return "hoch"
    if load >= 30:
        return "moderat"
    return "locker"


def training_trend(activities: list[dict], today: Optional[date] = None) -> dict:
    """Strava-aehnlicher Fitness/Fatigue/Form-Blick auf vorhandene Activities."""
    current = today or date.today()
    events = []
    for activity in activities:
        activity_date = _parse_date(activity.get("start_time"))
        if not activity_date:
            continue
        load = _num(activity.get("load"))
        if load is None:
            load = activity_load(activity)["load"]
        events.append((activity_date, load))

    if not events:
        return {
            "fitness": 0,
            "fatigue": 0,
            "form": 0,
            "weekly_load": 0,
            "projected_weekly_load": 0,
            "load_status": "keine Daten",
            "calibration": "keine Aktivitäten",
        }

    weekly_load = round(sum(load for d, load in events if d >= current - timedelta(days=current.weekday())), 1)
    day_of_week = current.weekday() + 1
    projected = round(weekly_load / day_of_week * 7, 1)
    fitness = round(_ewma(events, current, tau_days=42), 1)
    fatigue = round(_ewma(events, current, tau_days=7), 1)
    form = round(fitness - fatigue, 1)
    span_days = max(1, (current - min(d for d, _ in events)).days + 1)

    if projected >= 450:
        load_status = "hoch"
    elif projected >= 220:
        load_status = "aufbauend"
    elif projected >= 90:
        load_status = "locker"
    else:
        load_status = "niedrig"

    calibration = "stabil" if span_days >= 21 else f"Kalibrierung: {span_days}/21 Tage"
    return {
        "fitness": fitness,
        "fatigue": fatigue,
        "form": form,
        "weekly_load": weekly_load,
        "projected_weekly_load": projected,
        "load_status": load_status,
        "calibration": calibration,
    }


def calculate_readiness(snapshot: dict, sleep_goal_minutes: int = 480, recent_activities: Optional[list[dict]] = None) -> dict:
    sleep_minutes = _num(snapshot.get("sleep_duration_minutes"))
    sleep_debt = max(0, sleep_goal_minutes - int(sleep_minutes or 0)) if sleep_minutes else sleep_goal_minutes

    components = [
        _sleep_component(snapshot, sleep_goal_minutes),
        _hrv_component(snapshot),
        _body_battery_component(snapshot),
        _stress_component(snapshot),
        _garmin_readiness_component(snapshot),
    ]

    if recent_activities is not None:
        components.append(_load_component(recent_activities))

    available = [c for c in components if c.score >= 0]
    if not available:
        score = 50
    else:
        weights = _component_weights()
        weighted = sum(c.score * weights.get(c.name, 0.1) for c in available)
        total_weight = sum(weights.get(c.name, 0.1) for c in available)
        score = clamp(weighted / total_weight)

    readiness = Readiness(
        score=score,
        status=score_status(score),
        recommendation=_readiness_recommendation(score),
        intensity=_readiness_intensity(score),
        components=available,
        limiting_factors=[c.reason for c in sorted(available, key=lambda c: c.score) if c.score < 70],
        sleep_debt_minutes=sleep_debt,
        calibration=_calibration_status(snapshot, recent_activities),
    )
    return readiness.to_dict()


def weekly_goal_summary(gym_days: int, run_days: int, gym_goal: int = 3, run_goal: int = 3) -> dict:
    return {
        "gym_goal": gym_goal,
        "run_goal": run_goal,
        "gym_remaining": max(0, gym_goal - gym_days),
        "run_remaining": max(0, run_goal - run_days),
        "goal_status": "erfüllt" if gym_days >= gym_goal and run_days >= run_goal else "offen",
    }


def body_trend(history: list[dict], days: int) -> dict:
    if not history:
        return {"available": False}

    latest = history[-1]
    oldest = history[0]
    weights = [r["weight_kg"] for r in history if r.get("weight_kg")]
    recent_cutoff = date.today() - timedelta(days=7)
    recent_weights = [
        r["weight_kg"]
        for r in history
        if r.get("weight_kg") and _parse_date(r.get("date")) and _parse_date(r.get("date")) >= recent_cutoff
    ]
    span = _date_span_days(oldest.get("date"), latest.get("date"))

    def delta_per_week(key: str) -> Optional[float]:
        if span <= 0 or oldest.get(key) is None or latest.get(key) is None:
            return None
        return round((latest[key] - oldest[key]) / span * 7, 2)

    measurement_density = round(len(history) / max(1, days) * 7, 1)
    if measurement_density >= 2:
        measurement_quality = "gut"
    elif measurement_density >= 1:
        measurement_quality = "ok"
    else:
        measurement_quality = "lückenhaft"

    return {
        "avg_weight_7d": round(sum(recent_weights) / len(recent_weights), 2) if recent_weights else None,
        "avg_weight": round(sum(weights) / len(weights), 2) if weights else None,
        "weight_delta_per_week": delta_per_week("weight_kg"),
        "fat_delta_per_week": delta_per_week("body_fat_pct"),
        "muscle_delta_per_week": delta_per_week("muscle_mass_kg"),
        "measurement_density_per_week": measurement_density,
        "measurement_quality": measurement_quality,
    }


def _zone_load(zones: list[dict], minutes: float) -> Optional[float]:
    if not zones or minutes <= 0:
        return None
    total = 0.0
    has_value = False
    for zone in zones:
        zone_no = int(zone.get("zone") or 0)
        weight = _ZONE_WEIGHTS.get(zone_no)
        if weight is None:
            continue
        secs = _num(zone.get("secs"))
        pct = _num(zone.get("pct"))
        if secs:
            zone_minutes = secs / 60
        elif pct:
            zone_minutes = minutes * pct / 100
        else:
            continue
        total += zone_minutes * weight
        has_value = True
    return total if has_value else None


def _fallback_activity_load(activity: dict, minutes: float, sport_weight: float) -> tuple[float, str]:
    aerobic = _num(activity.get("training_effect_aerobic"))
    anaerobic = _num(activity.get("training_effect_anaerobic"))
    if aerobic or anaerobic:
        te = max(aerobic or 0, anaerobic or 0)
        return minutes * max(0.7, min(3.5, te / 1.6)) * sport_weight, "training_effect"

    avg_hr = _num(activity.get("avg_hr"))
    if avg_hr:
        intensity = max(0.7, min(3.0, 0.65 + (avg_hr - 95) / 55))
        return minutes * intensity * sport_weight, "avg_hr"

    return minutes * 0.8 * sport_weight, "duration"


def _sleep_component(snapshot: dict, goal_minutes: int) -> ComponentScore:
    score = _num(snapshot.get("sleep_score"))
    sleep = _num(snapshot.get("sleep_duration_minutes"))
    if score is None and sleep is not None:
        score = min(100, sleep / goal_minutes * 100)
    if score is None:
        return ComponentScore("sleep", -1, "k.A.", "Schlafdaten fehlen")
    sleep_debt = max(0, goal_minutes - int(sleep or 0))
    reason = "Schlafschuld" if sleep_debt >= 60 else "Schlaf ok"
    return ComponentScore("sleep", clamp(score), score_status(clamp(score)), reason)


def _hrv_component(snapshot: dict) -> ComponentScore:
    status = (snapshot.get("hrv_status") or "").upper()
    mapping = {
        "BALANCED": 88,
        "GOOD": 90,
        "UNBALANCED": 58,
        "LOW": 35,
        "POOR": 35,
    }
    if status in mapping:
        score = mapping[status]
    else:
        hrv = _num(snapshot.get("avg_hrv"))
        weekly = _num(snapshot.get("hrv_weekly_avg"))
        if hrv is None or weekly is None or weekly <= 0:
            return ComponentScore("hrv", -1, "k.A.", "HRV-Basis fehlt")
        score = clamp(70 + (hrv / weekly - 1) * 100)
    reason = "HRV unter Baseline" if score < 70 else "HRV stabil"
    return ComponentScore("hrv", clamp(score), score_status(clamp(score)), reason)


def _body_battery_component(snapshot: dict) -> ComponentScore:
    value = _num(snapshot.get("body_battery"))
    if value is None:
        return ComponentScore("body_battery", -1, "k.A.", "Body Battery fehlt")
    reason = "Body Battery niedrig" if value < 55 else "Energie ok"
    return ComponentScore("body_battery", clamp(value), score_status(clamp(value)), reason)


def _stress_component(snapshot: dict) -> ComponentScore:
    stress = _num(snapshot.get("avg_stress"))
    if stress is None:
        return ComponentScore("stress", -1, "k.A.", "Stressdaten fehlen")
    score = clamp(100 - stress)
    reason = "Stress erhöht" if stress > 35 else "Stress niedrig"
    return ComponentScore("stress", score, score_status(score), reason)


def _garmin_readiness_component(snapshot: dict) -> ComponentScore:
    score = _num(snapshot.get("training_readiness_score"))
    if score is None:
        return ComponentScore("garmin_readiness", -1, "k.A.", "Garmin Readiness fehlt")
    score = clamp(score)
    return ComponentScore("garmin_readiness", score, score_status(score), "Garmin Readiness limitiert" if score < 70 else "Garmin Readiness ok")


def _load_component(activities: list[dict]) -> ComponentScore:
    today = date.today()
    last_two_days = [
        a for a in activities
        if _parse_date(a.get("start_time")) and _parse_date(a.get("start_time")) >= today - timedelta(days=1)
    ]
    load = sum((_num(a.get("load")) if _num(a.get("load")) is not None else activity_load(a)["load"]) for a in last_two_days)
    if load >= 180:
        score = 45
    elif load >= 110:
        score = 65
    else:
        score = 85
    return ComponentScore("load", score, score_status(score), "hohe Last zuletzt" if score < 70 else "Last verträglich")


def _component_weights() -> dict[str, float]:
    return {
        "sleep": 0.25,
        "hrv": 0.20,
        "body_battery": 0.20,
        "stress": 0.15,
        "garmin_readiness": 0.15,
        "load": 0.05,
    }


def _readiness_recommendation(score: int) -> str:
    if score >= 80:
        return "Hart trainieren"
    if score >= 67:
        return "Normal trainieren"
    if score >= 52:
        return "Locker bewegen"
    return "Ruhetag"


def _readiness_intensity(score: int) -> str:
    if score >= 80:
        return "intensiv"
    if score >= 67:
        return "moderat"
    if score >= 52:
        return "locker"
    return "erholen"


def _calibration_status(snapshot: dict, activities: Optional[list[dict]]) -> str:
    if not snapshot.get("avg_hrv") and not snapshot.get("hrv_status"):
        return "HRV kalibriert noch oder fehlt"
    if activities is not None:
        dates = {_parse_date(a.get("start_time")) for a in activities}
        dates.discard(None)
        if len(dates) < 7:
            return f"Trainingslast kalibriert: {len(dates)}/21 Tage"
    return "stabil"


def _ewma(events: list[tuple[date, float]], today: date, tau_days: int) -> float:
    alpha = 1 - exp(-1 / tau_days)
    by_day: dict[date, float] = {}
    for d, load in events:
        by_day[d] = by_day.get(d, 0) + load
    start = min(by_day)
    value = 0.0
    current = start
    while current <= today:
        value = value * (1 - alpha) + by_day.get(current, 0) * alpha
        current += timedelta(days=1)
    return value


def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _date_span_days(start, end) -> int:
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if not start_date or not end_date:
        return 0
    return max(0, (end_date - start_date).days)


def _num(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
