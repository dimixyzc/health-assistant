from datetime import date
from training_plan.huberman import build_huberman_week
from training_plan.plan import build_week


def test_restart_skips_pre_restart_days_and_preserves_book_order():
    week = build_week(date(2026, 11, 9), start_date=date(2026, 10, 1))
    assert [w.date for w in week] == ['2026-11-11', '2026-11-12', '2026-11-13', '2026-11-15']
    assert [w.kind for w in week] == ['strength', 'cardio', 'strength', 'cardio']
    assert 'Brust' in week[0].title


def test_new_week_has_three_strength_three_cardio_and_saturday_rest():
    week = build_huberman_week(date(2026, 11, 16))
    assert [date.fromisoformat(w.date).weekday() for w in week if w.kind == 'strength'] == [0, 2, 4]
    assert [date.fromisoformat(w.date).weekday() for w in week if w.kind == 'cardio'] == [1, 3, 6]
    assert all(e.load_kg is None for w in week for e in w.exercises)


def test_elapsed_time_does_not_enable_hard_intervals_or_failure():
    week = build_huberman_week(date(2026, 12, 7))
    tuesday = next(w for w in week if w.date == '2026-12-10')
    assert 'keine Sprints' in tuesday.main_set
    assert all('Reserve' in e.notes for w in week for e in w.exercises)
    target = build_huberman_week(date(2026, 12, 7), target=True)
    tuesday = next(w for w in target if w.date == '2026-12-10')
    assert '6 Runden' in tuesday.main_set
    assert tuesday.estimated_minutes == 24
    assert all(e.rest_seconds >= 120 for w in target for e in w.exercises)


def test_book_sequence_wraps_across_week_boundary_with_saturday_rest():
    weeks = build_huberman_week(date(2026, 11, 16)) + build_huberman_week(date(2026, 11, 23))
    assert all(date.fromisoformat(w.date).weekday() != 5 for w in weeks)
    by_date = {w.date: w for w in weeks}
    assert 'Lange ruhige' in by_date['2026-11-22'].title
    assert by_date['2026-11-23'].title == 'Beine'
    assert 'Brust' in by_date['2026-11-18'].title
    assert 'Mittlere' in by_date['2026-11-24'].title
    assert 'Intervalle' in by_date['2026-11-19'].title
