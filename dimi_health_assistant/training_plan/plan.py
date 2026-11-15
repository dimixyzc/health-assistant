from __future__ import annotations

from datetime import date, timedelta

from .models import Exercise, Workout
from .profile import load_profile

CARDIO_ORDER = ("SkiErg", "Crosstrainer", "Indoor Cycling")


def _week_dates(start: date, monday: date) -> list[date]:
    return [monday + timedelta(days=i) for i in range(7) if monday + timedelta(days=i) >= start]


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def build_week(
    monday: date,
    *,
    start_date: date,
    cardio_minutes: int = 30,
    first_cardio_minutes: int | None = None,
    sunday_cardio_enabled: bool = False,
    cardio_sessions_completed: int = 0,
    strength_sets: int = 2,
) -> list[Workout]:
    """Create one week's conservative scaffold; weights require real history."""
    # The new book protocol replaces the old scaffold from the restart onward.
    from .huberman import START, build_huberman_week
    if monday >= week_start(START):
        return build_huberman_week(monday)

    if monday.weekday() != 0:
        raise ValueError("monday must be a Monday")
    if strength_sets not in (2, 3):
        raise ValueError("strength_sets must be 2 or 3")
    dates = _week_dates(start_date, monday)
    result: list[Workout] = []
    cardio_days = {1, 3} | ({6} if sunday_cardio_enabled else set())
    cardio_index = 0
    for day in dates:
        weekday = day.weekday()
        if weekday == 5:
            continue
        if weekday in {0, 2, 4}:
            templates = load_profile()['legacy_exercises'][str(weekday)]
            exercises = tuple(Exercise(**{**item, 'sets': strength_sets}) for item in templates)
            result.append(Workout(
                date=day.isoformat(), kind="strength", title="Ganzkörper Kraft — Reha-angepasster Einstieg",
                warmup="",
                exercises=exercises,
                main_set="Paarweise arbeiten: pro Runde einen Satz der ersten Übung, direkt danach einen Satz der Partnerübung; dann 60–75 s Pause. Runden pro Paar gemäß Satzanzahl wiederholen. Wenn möglich, gepaarte Geräte nahe beieinander wählen.",
                cooldown="3 Min. locker auslaufen oder gehen.", estimated_minutes=28 if strength_sets == 2 else 34,
                rationale="Übungsauswahl aus deiner Reha-Rückmeldung; Zielgewichte bleiben offen, bis eine vergleichbare Startleistung erfasst ist.",
                warnings=("Reha-Phase: nur Körpergewicht/sehr leichte Last; kein automatisches Steigern bei fehlender Rückmeldung.",),
            ))
        elif weekday in cardio_days:
            modality = CARDIO_ORDER[min(cardio_index, len(CARDIO_ORDER) - 1)]
            session_minutes = first_cardio_minutes if cardio_index == 0 and first_cardio_minutes is not None else cardio_minutes
            use_intervals = cardio_sessions_completed >= 1 and weekday == 3
            interval_text = (
                f"{max(8, session_minutes - 12)} Min. gleichmäßig plus 3 × 1 Min. zügig, dazwischen je 2 Min. locker; RPE höchstens 7/10, kein All-out."
                if use_intervals
                else f"{max(5, session_minutes - 5)} Min. gleichmäßig, kontrolliert fordernd bei RPE 4–6/10; keine Intervalle."
            )
            result.append(Workout(
                date=day.isoformat(), kind="cardio", title=f"{modality} — Ausdauer / VO₂-Aufbau",
                warmup="",
                main_set=interval_text,
                cooldown="5 Min. locker.", estimated_minutes=session_minutes,
                completion_criteria="Belastung etwa RPE 4–6/10; in zügigen Abschnitten RPE höchstens 7/10. Kniebeschwerden, Schwellung, Instabilität oder Verschlechterung: stoppen und keine Progression.",
                rationale="Nach Cardio-Pause fordernder, aber submaximaler Wiedereinstieg; steigern erst nach Rückmeldung und Vergleich der Herzfrequenzkurve.",
                warnings=("Herzfrequenz ist ein ergänzendes Signal, kein alleiniger Belastungsregler.",),
            ))
            cardio_index += 1
    return result


def adjust_cardio_minutes(planned_minutes: int, *, completed: bool, rpe: int | None,
                          symptoms: bool, hr_trace_available: bool) -> tuple[int, str]:
    """Deterministic next-week duration update; never increase on HR alone."""
    if symptoms:
        return planned_minutes, "Sicherheitsstopp: Zeit und Intensität nicht steigern; betroffene Einheit prüfen."
    if not completed or rpe is None:
        return planned_minutes, "Zu wenig Rückmeldung: Umfang unverändert lassen."
    if rpe >= 8:
        return max(10, planned_minutes - 5), "Sehr hohe subjektive Anstrengung: nächste Einheit um 5 Minuten kürzen."
    if rpe <= 6 and completed:
        basis = "Herzfrequenzkurve zusätzlich prüfen." if hr_trace_available else "Ohne Herzfrequenzkurve vorsichtig anhand RPE anpassen."
        return min(planned_minutes + 5, 45), f"Gut bewältigt: höchstens 5 Minuten ergänzen. {basis}"
    return planned_minutes, "Belastung passend oder unklar: Umfang halten."


def suggest_load_progression(previous_load_kg: float | None, *, target_reps: int,
                             completed_reps: int | None, rpe: int | None,
                             symptoms: bool, smallest_available_increment_kg: float | None) -> tuple[float | None, str]:
    """Only progress a comparable lift when achieved reps/effort and available plates are known."""
    if symptoms:
        return previous_load_kg, "Sicherheitsstopp: Last nicht erhöhen; betroffene Übung prüfen."
    if previous_load_kg is None or completed_reps is None or rpe is None:
        return previous_load_kg, "Fehlende Last-, Wiederholungs- oder Anstrengungsdaten: Last unverändert lassen."
    if completed_reps < target_reps or rpe >= 9:
        return previous_load_kg, "Zielwiederholungen nicht kontrolliert erreicht oder sehr hohe Anstrengung: Last halten."
    if smallest_available_increment_kg is None or smallest_available_increment_kg <= 0:
        return previous_load_kg, "Verfügbare Gewichtsstufe unbekannt: Last halten."
    return round(previous_load_kg + smallest_available_increment_kg, 2), "Ziel erreicht; um genau eine verfügbare Gewichtsstufe steigern."


def choose_strength_sets(recent_sessions: list[dict]) -> tuple[int, str]:
    """Use two work sets until two recent sessions have explicit easy RPE and no symptoms."""
    if len(recent_sessions) < 2:
        return 2, "Einstiegsumfang: weniger als zwei aktuelle Krafteinheiten mit Rückmeldung."
    last_two = recent_sessions[-2:]
    if any(session.get("symptoms") for session in last_two):
        return 2, "Sicherheitsstopp: Beschwerden gemeldet; Satzanzahl nicht erhöhen."
    if any(session.get("rpe") is None for session in last_two):
        return 2, "RPE fehlt; Satzanzahl nicht erhöhen."
    if all(int(session["rpe"]) <= 7 for session in last_two):
        return 3, "Zwei aktuelle Einheiten bei RPE ≤7 ohne gemeldete Beschwerden; einen Satz je Übung ergänzen."
    return 2, "Anstrengung war hoch; Satzanzahl beibehalten."
