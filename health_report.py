"""Produce a privacy-minimal daily health report for a Codex automation.

The script deliberately emits data, not an LLM-written recommendation.  This
lets the scheduled ChatGPT/Codex task provide the coaching in the chat without
requiring an OpenAI Platform API key.
"""

import argparse
import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from analytics import insights
from config import settings
from knowledge import KnowledgeBase
from knowledge.library import EVIDENCE_POLICY
from storage import database as db


LOCAL_TZ = ZoneInfo("Europe/Berlin")


def _compact(value):
    """Omit missing fields; preserve measured zero and explicit false values."""
    if isinstance(value, dict):
        result = {key: _compact(item) for key, item in value.items()}
        return {key: item for key, item in result.items() if item is not None and item != "" and item != {} and item != []}
    if isinstance(value, list):
        return [_compact(item) for item in value]
    return value


def _week_context(weekly: dict) -> dict:
    """Keep the payload compact while preserving the relevant trend signals."""
    keys = (
        "week_start",
        "week_end",
        "gym_days",
        "gym_goal",
        "gym_remaining",
        "cardio_days",
        "cardio_goal",
        "cardio_remaining",
        "total_load",
        "training_trend",
        "avg_sleep_minutes",
        "avg_sleep_score",
        "avg_deep_sleep_minutes",
        "avg_rem_sleep_minutes",
        "long_term_metrics",
        "long_term_changes",
    )
    return {key: weekly.get(key) for key in keys}


def _activities_for_date(activities: list[dict], target_date: str) -> list[dict]:
    """Return only today's activities, matching the legacy evening summary."""
    return [
        activity
        for activity in activities
        if str(activity.get("start_time", "")).startswith(target_date)
    ]


async def build_report(report_type: str) -> dict:
    await db.init_db(settings.data_dir)

    # Renpho is fetched before calculating the trend, so today's measurement
    # is included when one is available.
    renpho_error = None
    try:
        await insights.refresh_renpho_cache()
    except Exception as exc:  # A Garmin report remains useful without Renpho.
        renpho_error = str(exc)

    # The training plan already collects the daily snapshot, the current week
    # and activities. This keeps morning and evening reports consistent.
    plan = await insights.get_training_plan()
    snapshot = plan.get("snapshot", {})
    weekly = plan.get("weekly") or {}
    weight_trend = await insights.get_weight_trend(days=30)
    experiments = await db.get_active_experiments(settings.data_dir)

    report = {
        "report_type": report_type,
        "coaching_policy": EVIDENCE_POLICY,
        "knowledge_context": KnowledgeBase(settings.data_dir, settings.knowledge_book_path).context(
            "Schlaf Erholung Stress Ernährung" if report_type == "morning" else "Schlaf Abendroutine Stress"
        ),
        "generated_at": datetime.now(LOCAL_TZ).isoformat(timespec="minutes"),
        "timezone": "Europe/Berlin",
        "daily_snapshot": snapshot,
        "week_context": _week_context(weekly),
        "weight_trend_30_days": weight_trend,
        "active_experiments": experiments,
        "care_context": {
            "knee_rehab_active": settings.knee_rehab_active,
            "focus": "Allgemeine Gesundheit und Erholung nach Knie-Operation",
            "activity_interpretation": (
                "Schritte, Gym und Cardio sind Kontextdaten, keine Ziele. "
                "Keine Trainings- oder Belastungsempfehlungen ohne medizinische Freigabe."
            ) if settings.knee_rehab_active else "Normale Trainingsauswertung aktiv.",
        },
    }
    if report_type == "morning":
        report["suggested_session"] = plan.get("suggested_session")
    else:
        report["today_activities"] = _activities_for_date(
            weekly.get("activities") or [], snapshot.get("date", "")
        )
    if renpho_error:
        report["renpho_fetch_error"] = renpho_error
    # Long-term values already occur in week_context; keep changes in the
    # daily snapshot and avoid serializing the same values twice.
    report["daily_snapshot"] = {key: value for key, value in snapshot.items() if key != "long_term_metrics"}
    return _compact(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a health-coach data report.")
    parser.add_argument(
        "--report",
        choices=("morning", "evening"),
        default="morning",
        help="Select the data context for the morning or evening check-in.",
    )
    parser.add_argument("--pretty", action="store_true", help="Format JSON for human reading.")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(build_report(args.report)),
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
            default=str,
        )
    )


if __name__ == "__main__":
    main()
