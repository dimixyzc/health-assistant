from __future__ import annotations

from statistics import fmean
from typing import Any


def heart_rate_comparison(activities: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compare the two latest similar cardio sessions; do not infer effort from HR alone."""
    cardio = [a for a in activities if any(key in a["activity_type"].lower()
              for key in ("cycling", "rowing", "elliptical", "cardio", "ski"))]
    if not cardio:
        return None
    latest = cardio[-1]
    latest_trace = latest.get("hr_samples") or []
    latest_hr = [float(point["bpm"]) for point in latest_trace if point.get("bpm") is not None]
    for previous in reversed(cardio[:-1]):
        if previous["activity_type"] != latest["activity_type"]:
            continue
        latest_seconds = latest.get("duration_seconds") or 0
        previous_seconds = previous.get("duration_seconds") or 0
        if not latest_seconds or not previous_seconds or abs(latest_seconds - previous_seconds) / previous_seconds > 0.15:
            continue
        previous_hr = [float(point["bpm"]) for point in previous.get("hr_samples", [])
                       if point.get("bpm") is not None]
        if len(latest_hr) < 10 or len(previous_hr) < 10:
            continue
        return {
            "latest_date": latest["local_start"],
            "compared_with_date": previous["local_start"],
            "activity_type": latest["activity_type"],
            "average_hr_delta_bpm": round(fmean(latest_hr) - fmean(previous_hr), 1),
            "max_hr_delta_bpm": round(max(latest_hr) - max(previous_hr), 1),
            "rpe_latest": latest.get("rpe"),
            "rpe_previous": previous.get("rpe"),
            "interpretation": "Context only: compare only at similar modality and duration; pace/power, RPE, symptoms and measurement quality are needed before changing a target.",
        }
    return {"latest_date": latest["local_start"], "activity_type": latest["activity_type"],
            "comparison": "No sufficiently similar prior cardio trace; this session establishes a baseline."}


def strength_exercise_history(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize exact Garmin exercise names; never merge guessed variants."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for activity in activities:
        for item in activity.get("strength_sets", []):
            if item.get("set_type", "").upper() == "REST":
                continue
            grouped.setdefault(item["exercise_name"], []).append({
                "date": activity["local_start"][:10],
                "reps": item.get("reps"),
                "load_kg": item.get("load_kg"),
            })
    result = []
    for name, sets in sorted(grouped.items()):
        result.append({
            "exercise": name,
            "sessions": sorted({item["date"] for item in sets}),
            "set_count": len(sets),
            "latest_loads_kg": sorted({item["load_kg"] for item in sets
                                        if item["load_kg"] is not None and item["load_kg"] > 0}),
            "latest_reps": [item["reps"] for item in sets if item["reps"] is not None],
            "comparable_progressions": len({item["date"] for item in sets}) >= 2,
        })
    return result
