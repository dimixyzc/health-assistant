from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

from .config import Settings
from .analysis import heart_rate_comparison, strength_exercise_history
from .garmin import GarminReader
from .plan import adjust_cardio_minutes, build_week, choose_strength_sets, week_start
from .storage import Store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="training-plan")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="Import Garmin activities and compact HR traces")
    imp.add_argument("--since", type=date.fromisoformat, default=None,
                     help="Backfill override; otherwise resumes from the previous successful import with a 14-day overlap")
    imp.add_argument("--until", type=date.fromisoformat, default=date.today())
    feedback = sub.add_parser("feedback", help="Record effort and symptoms for a completed session")
    feedback.add_argument("activity_id")
    feedback.add_argument("--rpe", type=int)
    feedback.add_argument("--symptoms", action="store_true")
    feedback.add_argument("--note", default="")
    sub.add_parser("week-analysis", help="Summarize recent cardio and strength activity data")
    preview = sub.add_parser("preview", help="Render the next week's deterministic plan")
    preview.add_argument("--week-of", type=date.fromisoformat, default=None)
    preview.add_argument("--huberman-target", action="store_true", help="Explicit target protocol after a tolerated break-in; enables hard intervals")
    preview.add_argument("--sunday-cardio", action="store_true")
    preview.add_argument("--no-sunday-cardio", action="store_true")
    dry_run = sub.add_parser("dry-run", help="Build Garmin payload preview only; never uploads")
    dry_run.add_argument("--no-sunday-cardio", action="store_true")
    sub.add_parser("publish", help="Publishing is disabled pending a separately confirmed test workout")
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        settings = Settings.from_env()
        store = Store(settings.data_dir / "training_plan.sqlite3")
        if args.command == "import":
            previous_through = store.get_sync_state("activity_import_through")
            if args.since:
                import_start = args.since
            elif previous_through:
                import_start = max(settings.initial_import_since,
                                   date.fromisoformat(previous_through) - timedelta(days=14))
            else:
                import_start = settings.initial_import_since
            if args.until < import_start:
                raise ValueError("--until must be on or after --since")
            reader = GarminReader(settings.garmin_email, settings.garmin_password,
                                  str(settings.garmin_token_dir))
            reader.login()
            activities = reader.fetch_activities(import_start, args.until)
            for activity in activities:
                store.upsert_activity(activity)
            vo2_data_available = False
            try:
                estimates = reader.fetch_vo2_estimates(import_start, args.until)
                store.upsert_vo2_estimates(estimates)
                vo2_data_available = bool(estimates)
            except Exception:
                # VO2 history is optional; don't fail an activity import if this endpoint is unavailable.
                pass
            store.set_sync_state("activity_import_through", args.until.isoformat())
            print(json.dumps({"imported_or_updated": len(activities), "from": import_start.isoformat(),
                              "through": args.until.isoformat(),
                              "vo2_estimates_available": vo2_data_available}, ensure_ascii=False, indent=2))
        elif args.command == "feedback":
            store.add_feedback(args.activity_id, args.rpe, args.symptoms, args.note)
            print("Feedback gespeichert.")
        elif args.command == "week-analysis":
            end = date.today()
            start = end - timedelta(days=13)
            rows = store.activities(start.isoformat(), end.isoformat())
            cardio = [a for a in rows if any(s in a["activity_type"].lower() for s in ("cycling", "rowing", "elliptical", "cardio", "ski"))]
            print(json.dumps({"period": [start.isoformat(), end.isoformat()], "activity_count": len(rows),
                              "cardio_count": len(cardio), "activities": [
                                  {"activity_id": a["activity_id"], "date": a["local_start"], "type": a["activity_type"],
                                   "minutes": round(a["duration_seconds"] / 60), "average_hr": a["average_hr"],
                                   "max_hr": a["max_hr"], "hr_trace_points": len(a["hr_samples"]),
                                  "rpe": a["rpe"], "symptoms_reported": bool(a["symptoms"])} for a in rows],
                              "heart_rate_comparison": heart_rate_comparison(rows),
                              "strength_exercise_history": strength_exercise_history(rows),
                              "garmin_vo2_estimates": store.vo2_estimates()},
                             ensure_ascii=False, indent=2))
        elif args.command in {"preview", "dry-run"}:
            monday = args.week_of if args.command == "preview" and args.week_of else week_start(max(settings.start_date, date.today()))
            if monday.weekday() != 0:
                raise ValueError("--week-of must be a Monday")
            from .huberman import START, build_huberman_week
            if monday >= week_start(START):
                target = getattr(args, "huberman_target", False)
                workouts = build_huberman_week(monday, target=target)
                store.record_previews(workouts)
                print(json.dumps({"mode": "DRY_RUN", "week_of": monday.isoformat(),
                                  "protocol": "Huberman book", "phase": "target" if target else "break-in",
                                  "rest_day": "Saturday", "garmin_published": False,
                                  "workouts": [w.to_dict() for w in workouts]}, ensure_ascii=False, indent=2))
                store.close()
                return
            sunday = False if getattr(args, "no_sunday_cardio", False) else (
                getattr(args, "sunday_cardio", False) or settings.sunday_cardio_enabled)
            cardio_history = store.count_cardio_since(settings.cardio_baseline_date.isoformat())
            prev_rows = store.activities(settings.cardio_baseline_date.isoformat(),
                                         (monday - timedelta(days=1)).isoformat())
            strength_rows = store.activities(max(settings.start_date, monday - timedelta(days=14)).isoformat(),
                                             (monday - timedelta(days=1)).isoformat())
            recent_strength = [row for row in strength_rows if "strength" in row["activity_type"].lower()]
            strength_sets, strength_reason = choose_strength_sets(recent_strength)
            previous_cardio = [row for row in prev_rows if any(s in row["activity_type"].lower()
                               for s in ("cycling", "rowing", "elliptical", "cardio", "ski"))]
            cardio_adjustment = {"minutes": settings.cardio_minutes, "reason": "Noch keine passende absolvierte Cardio-Einheit mit Rückmeldung; Ausgangsdauer beibehalten."}
            first_cardio_type = {"SkiErg": ("rowing", "indoor_rowing", "cardio"),
                                 "Crosstrainer": ("elliptical",),
                                 "Indoor Cycling": ("cycling",)}["SkiErg"]
            comparable_previous = [row for row in previous_cardio
                                   if any(alias in row["activity_type"].lower() for alias in first_cardio_type)]
            if comparable_previous:
                last = comparable_previous[-1]
                minutes, reason = adjust_cardio_minutes(settings.cardio_minutes, completed=True,
                    rpe=last.get("rpe"), symptoms=bool(last.get("symptoms")),
                    hr_trace_available=bool(last.get("hr_samples")))
                cardio_adjustment = {"minutes": minutes, "reason": reason}
            workouts = build_week(monday, start_date=settings.start_date,
                                  cardio_minutes=settings.cardio_minutes,
                                  first_cardio_minutes=cardio_adjustment["minutes"],
                                  sunday_cardio_enabled=sunday,
                                  cardio_sessions_completed=cardio_history,
                                  strength_sets=strength_sets)
            store.record_previews(workouts)
            print(json.dumps({"mode": "DRY_RUN", "week_of": monday.isoformat(),
                              "post_baseline_cardio_sessions": cardio_history,
                              "heart_rate_comparison": heart_rate_comparison(prev_rows),
                              "cardio_adjustment": cardio_adjustment,
                              "strength_adjustment": {"sets_per_exercise": strength_sets, "reason": strength_reason},
                              "planned_workout_count": len(workouts),
                              "garmin_calendar_diff": "unknown; calendar is not read in DRY_RUN",
                              "workouts": [workout.to_dict() for workout in workouts]},
                             ensure_ascii=False, indent=2))
        else:
            print("Publishing is disabled. First preview and validate one test workout, then confirm that exact upload.", file=sys.stderr)
            raise SystemExit(2)
        store.close()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
