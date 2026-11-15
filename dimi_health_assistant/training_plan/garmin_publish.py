"""Local Codex payload previews only. This module never performs Garmin writes."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
import re
from .profile import load_profile


def build_ski_erg_workout() -> dict[str, Any]:
    return deepcopy(load_profile()['publish_templates']['cardio'])


def update_strength_descriptions(workout: dict[str, Any], activities: list[dict[str, Any]]) -> None:
    """Put exact-name loads from the latest completed session first; change only text."""
    latest: dict[str, list[float | None]] = {}
    for activity in sorted(activities, key=lambda item: item["local_start"]):
        session: dict[str, list[float | None]] = {}
        for item in activity.get("strength_sets", []):
            if item.get("set_type", "").upper() == "REST" or not item.get("reps"):
                continue
            session.setdefault(item["exercise_name"], []).append(item.get("load_kg"))
        latest.update(session)

    def walk(steps):
        for step in steps:
            name = step.get("exerciseName")
            if name:
                values = latest.get(name, [])
                loads = sorted({value for value in values if value is not None})
                if loads:
                    formatted = "/".join(f"{value:g}".replace(".", ",") for value in loads)
                    prefix = f"Zuletzt {formatted} kg"
                    if loads == [0]:
                        prefix += " erfasst"
                    if None in values:
                        prefix += " (teils ohne Angabe)"
                    prefix += "."
                else:
                    prefix = "Letzte Last unbekannt."
                old = step.get("description") or ""
                reps = re.search(r"(\d+(?:[–-]\d+)?)(?: je Seite)? Wdh\.", old)
                side_reps = re.search(r"(\d+(?:[–-]\d+)?) je Seite", old)
                count = reps.group(1) if reps else side_reps.group(1) if side_reps else f"{step.get('endConditionValue', 0):g}"
                hint = f"{count} Wdh."
                if "je Seite" in old and "je Seite" not in hint:
                    hint = hint.replace(" Wdh.", " Wdh. je Seite.")
                target = load_profile(required=False).get("description_targets", {}).get(name)
                if target:
                    hint += " " + target
                step["description"] = f"{prefix} {hint}"
            walk(step.get("workoutSteps", []))

    for segment in workout.get("workoutSegments", []):
        walk(segment.get("workoutSteps", []))


def build_first_strength_workout(activities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    workout = deepcopy(load_profile()['publish_templates']['strength'])
    update_strength_descriptions(workout, activities or [])
    return workout
