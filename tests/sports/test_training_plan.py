from datetime import date

from training_plan.analysis import heart_rate_comparison, strength_exercise_history
from training_plan.garmin import _extract_heart_rate_trace, extract_strength_sets, extract_vo2_estimates
from training_plan.garmin_publish import build_first_strength_workout, build_ski_erg_workout, update_strength_descriptions
from training_plan.plan import adjust_cardio_minutes, build_week, choose_strength_sets, suggest_load_progression, week_start
from training_plan.storage import Store


def test_initial_week_respects_start_date_and_weekdays():
    monday = week_start(date(2026, 10, 1))
    workouts = build_week(monday, start_date=date(2026, 10, 1), cardio_minutes=30)
    assert [w.date for w in workouts] == ["2026-10-01", "2026-10-02"]
    assert [w.kind for w in workouts] == ["cardio", "strength"]


def test_saturday_always_free_and_sunday_requires_opt_in():
    workouts = build_week(date(2026, 10, 5), start_date=date(2026, 10, 1), sunday_cardio_enabled=False)
    assert all(date.fromisoformat(w.date).weekday() != 5 for w in workouts)
    assert all(date.fromisoformat(w.date).weekday() != 6 for w in workouts)
    enabled = build_week(date(2026, 10, 5), start_date=date(2026, 10, 1), sunday_cardio_enabled=True)
    assert "2026-10-11" in [w.date for w in enabled]


def test_strength_schedule_is_monday_wednesday_friday():
    workouts = build_week(date(2026, 10, 5), start_date=date(2026, 10, 1))
    assert [date.fromisoformat(w.date).weekday() for w in workouts if w.kind == "strength"] == [0, 2, 4]


def test_every_strength_workout_fits_35_minutes_and_uses_alternating_pairs():
    for sets in (2, 3):
        workouts = build_week(date(2026, 10, 5), start_date=date(2026, 10, 1), strength_sets=sets)
        strength = [w for w in workouts if w.kind == "strength"]
        assert strength
        for workout in strength:
            assert workout.estimated_minutes <= 35
            assert workout.estimated_minutes == (28 if sets == 2 else 34)
            assert workout.warmup == ""
            assert len(workout.exercises) == 6
            assert [e.pair_id for e in workout.exercises] == ["A", "A", "B", "B", "C", "C"]
            assert "pro Runde einen Satz" in workout.main_set
            assert "60–75 s Pause" in workout.main_set
    full_week = build_week(date(2026, 10, 5), start_date=date(2026, 10, 1), strength_sets=3)
    assert all(w.estimated_minutes <= 35 for w in full_week)


def test_strength_volume_only_increases_after_two_tolerated_sessions():
    assert choose_strength_sets([])[0] == 2
    assert choose_strength_sets([{"rpe": 6, "symptoms": False}])[0] == 2
    assert choose_strength_sets([{"rpe": 6, "symptoms": False}, {"rpe": 7, "symptoms": False}])[0] == 3
    assert choose_strength_sets([{"rpe": 6, "symptoms": False}, {"rpe": 5, "symptoms": True}])[0] == 2
    assert choose_strength_sets([{"rpe": 6, "symptoms": False}, {"rpe": None, "symptoms": False}])[0] == 2


def test_only_explicit_synthetic_baseline_has_target_weight():
    strength = next(w for w in build_week(date(2026, 10, 5), start_date=date(2026, 10, 1)) if w.kind == "strength")
    assert all(e.load_kg is None or e.load_kg == 0.0 for e in strength.exercises
               if e.name != "Langhantel-Kniebeuge / Back Squat")
    assert any(e.name == "Langhantel-Kniebeuge / Back Squat" and e.load_kg == 13.0 for e in strength.exercises)
    assert suggest_load_progression(None, target_reps=8, completed_reps=None, rpe=None,
                                    symptoms=False, smallest_available_increment_kg=None)[0] is None


def test_weight_progression_requires_reps_effort_and_increment():
    same, _ = suggest_load_progression(10, target_reps=8, completed_reps=7, rpe=7,
                                       symptoms=False, smallest_available_increment_kg=2.5)
    assert same == 10
    stepped, _ = suggest_load_progression(10, target_reps=8, completed_reps=8, rpe=7,
                                          symptoms=False, smallest_available_increment_kg=1.25)
    assert stepped == 11.25
    stopped, _ = suggest_load_progression(10, target_reps=8, completed_reps=10, rpe=5,
                                          symptoms=True, smallest_available_increment_kg=1.25)
    assert stopped == 10


def test_cardio_missing_data_and_symptoms_do_not_progress():
    assert adjust_cardio_minutes(30, completed=False, rpe=None, symptoms=False,
                                 hr_trace_available=False)[0] == 30
    assert adjust_cardio_minutes(30, completed=True, rpe=4, symptoms=True,
                                 hr_trace_available=True)[0] == 30
    assert adjust_cardio_minutes(30, completed=True, rpe=9, symptoms=False,
                                 hr_trace_available=True)[0] == 25


def test_activity_import_is_deduplicated_by_garmin_id(tmp_path):
    store = Store(tmp_path / "test.sqlite3")
    activity = {"activity_id": "abc", "local_start": "2026-10-01 09:00:00",
                "activity_type": "indoor_cycling", "duration_seconds": 1800,
                "average_hr": 120, "max_hr": 150, "distance_m": None, "hr_samples_json": "[]", "strength_sets_json": "[]"}
    store.upsert_activity(activity)
    store.upsert_activity({**activity, "average_hr": 121})
    assert store.count_cardio_since("2026-08-07") == 1
    rows = store.activities("2026-10-01", "2026-10-01")
    assert len(rows) == 1
    assert rows[0]["average_hr"] == 121
    store.close()


def test_hr_trace_extracts_only_hr_and_elapsed_values():
    detail = {"metricDescriptors": [
        {"key": "sumElapsedDuration", "metricsIndex": 0},
        {"key": "directHeartRate", "metricsIndex": 1}],
        "activityDetailMetrics": [{"metrics": [0, 70]}, {"metrics": [15, 100]},
                                  {"metrics": [30, 110]}]}
    assert _extract_heart_rate_trace(detail) == [
        {"elapsed_seconds": 0.0, "bpm": 70.0}, {"elapsed_seconds": 15.0, "bpm": 100.0},
        {"elapsed_seconds": 30.0, "bpm": 110.0}]


def test_calendar_dates_are_iso_and_plan_contains_no_saturday():
    workouts = build_week(date(2026, 10, 5), start_date=date(2026, 10, 1))
    assert all(date.fromisoformat(w.date).isoformat() == w.date for w in workouts)
    assert all(date.fromisoformat(w.date).weekday() != 5 for w in workouts)


def test_interval_is_limited_to_one_weekly_session_after_a_baseline():
    initial = build_week(date(2026, 10, 5), start_date=date(2026, 10, 1), sunday_cardio_enabled=True)
    assert all("keine Intervalle" in w.main_set for w in initial if w.kind == "cardio")
    assert all("25 Min. gleichmäßig" in w.main_set for w in initial if w.kind == "cardio")
    later = build_week(date(2026, 10, 5), start_date=date(2026, 10, 1),
                       sunday_cardio_enabled=True, cardio_sessions_completed=1)
    interval_sessions = [w for w in later if w.kind == "cardio" and "3 × 1 Min." in w.main_set]
    assert len(interval_sessions) == 1
    assert "kein All-out" in interval_sessions[0].main_set
    assert "18 Min. gleichmäßig plus 3 × 1 Min." in interval_sessions[0].main_set


def test_stable_ids_are_deterministic():
    workout = build_week(date(2026, 10, 5), start_date=date(2026, 10, 1))[0]
    assert workout.to_dict()["stable_id"] == workout.to_dict()["stable_id"]


def test_preview_register_is_idempotent(tmp_path):
    store = Store(tmp_path / "test.sqlite3")
    workout = build_week(date(2026, 10, 5), start_date=date(2026, 10, 1))[0]
    store.record_previews([workout])
    store.record_previews([workout])
    count = store.db.execute("SELECT COUNT(*) FROM sync_ledger").fetchone()[0]
    assert count == 1
    store.close()


def test_sync_cursor_persists_and_can_be_read(tmp_path):
    store = Store(tmp_path / "test.sqlite3")
    assert store.get_sync_state("activity_import_through") is None
    store.set_sync_state("activity_import_through", "2026-09-24")
    assert store.get_sync_state("activity_import_through") == "2026-09-24"
    store.close()


def test_vo2_extractor_keeps_only_dated_vo2_values():
    data = {"calendarDate": "2026-09-01", "vo2MaxValue": 42.5, "otherMetric": 9}
    assert extract_vo2_estimates(data) == [{"date": "2026-09-01", "metric_name": "vo2MaxValue", "value": 42.5}]


def test_strength_history_does_not_merge_exercise_variants_or_rest_sets():
    activities = [{"local_start": "2026-09-20 10:00", "strength_sets": [
        {"exercise_name": "LEG_PRESS", "set_type": "ACTIVE", "reps": 8, "load_kg": 0.0},
        {"exercise_name": "LEG_PRESS", "set_type": "REST", "reps": None, "load_kg": None},
    ]}]
    result = strength_exercise_history(activities)
    assert result == [{"exercise": "LEG_PRESS", "sessions": ["2026-09-20"], "set_count": 1,
                       "latest_loads_kg": [], "latest_reps": [8], "comparable_progressions": False}]


def test_heart_rate_comparison_requires_same_type_and_similar_duration():
    a = {"local_start": "2026-09-01", "activity_type": "indoor_cycling", "duration_seconds": 1800,
         "hr_samples": [{"bpm": 130.0}] * 10}
    b = {"local_start": "2026-09-08", "activity_type": "indoor_cycling", "duration_seconds": 1800,
         "hr_samples": [{"bpm": 135.0}] * 10}
    result = heart_rate_comparison([a, b])
    assert result["average_hr_delta_bpm"] == 5.0


def test_strength_set_parser_converts_grams_to_kg_and_skips_rest_sets():
    payload = {"exerciseSets": [{"exercises": [{"name": "DUMBBELL_BENCH_PRESS", "category": "BENCH_PRESS"}],
                                 "repetitionCount": 8, "weight": 12500, "setType": "ACTIVE"},
                                {"exercises": [], "repetitionCount": None, "weight": None, "setType": "REST"}]}
    parsed = extract_strength_sets(payload)
    assert parsed[0]["reps"] == 8
    assert parsed[0]["load_kg"] == 12.5
    assert parsed[0]["exercise_name"] == "DUMBBELL_BENCH_PRESS"
    assert len(parsed) == 1


def test_initial_garmin_workouts_are_structured_and_have_no_invented_loads():
    cardio = build_ski_erg_workout()
    assert cardio["workoutName"] == "SkiErg – Wiedereinstieg"
    assert cardio["estimatedDurationInSecs"] == 1800
    assert [step["endConditionValue"] for step in cardio["workoutSegments"][0]["workoutSteps"]] == [1500, 300]

    strength = build_first_strength_workout()
    pairs = strength["workoutSegments"][0]["workoutSteps"]
    assert len(pairs) == 3
    assert all(pair["numberOfIterations"] == 2 and len(pair["workoutSteps"]) == 3 for pair in pairs)
    assert all("weightValue" not in step for pair in pairs for step in pair["workoutSteps"][:2])


def test_watch_description_uses_latest_session_and_exact_exercise():
    steps = [{"exerciseName": "LEG_CURL", "description": "Beinbeuger: 10–12 Wdh. Langer Hinweis.",
              "weightValue": 23},
             {"exerciseName": "BARBELL_BACK_SQUAT", "description": "6–8 Wdh.", "weightValue": 17},
             {"exerciseName": "LAT_PULLDOWN", "description": "8–12 Wdh."}]
    workout = {"workoutSegments": [{"workoutSteps": [{"workoutSteps": steps}]}]}
    activities = [{"local_start": "1726-10-14", "strength_sets": [
        {"exercise_name": "LEG_CURL", "load_kg": 37, "reps": 8},
        {"exercise_name": "BARBELL_BACK_SQUAT", "load_kg": 0, "reps": 8}]},
        {"local_start": "1726-10-07", "strength_sets": [
            {"exercise_name": "LEG_CURL", "load_kg": 23, "reps": 8},
            {"exercise_name": "SQUAT", "load_kg": 17, "reps": 8},
            {"exercise_name": "LAT_PULLDOWN", "load_kg": 55, "reps": 8}]},
        {"local_start": "1726-10-15", "strength_sets": [
            {"exercise_name": "LAT_PULLDOWN", "load_kg": None, "reps": 8}]}]
    update_strength_descriptions(workout, activities)
    assert steps[0]["description"] == "Zuletzt 37 kg. 10–12 Wdh."
    assert steps[0]["weightValue"] == 23
    assert steps[1]["description"] == "Zuletzt 0 kg erfasst. 6–8 Wdh. Ziel 13 kg (synthetisch)."
    assert steps[2]["description"] == "Letzte Last unbekannt. 8–12 Wdh."


def test_pallof_description_preserves_per_side_range():
    step = {"exerciseName": "CABLE_CORE_PRESS", "endConditionValue": 16,
            "description": "Pallof Press: 8–10 je Seite; zuletzt 13 kg erfasst."}
    workout = {"workoutSegments": [{"workoutSteps": [step]}]}
    update_strength_descriptions(workout, [])
    assert step["description"] == "Letzte Last unbekannt. 8–10 Wdh. je Seite."
