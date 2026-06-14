"""
Template-basierter Fallback-Formatter für alle Message-Typen.
Wird genutzt wenn OpenAI nicht verfügbar ist.
"""
from datetime import date
from typing import Optional

_MONTHS_DE = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}

_WEEKDAYS_DE = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}


def fmt_date(iso: Optional[str]) -> str:
    """'2026-05-14' → '14. Mai 2026'"""
    if not iso:
        return "–"
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{d.day}. {_MONTHS_DE[d.month]} {d.year}"
    except Exception:
        return str(iso)


def fmt_date_short(iso: Optional[str]) -> str:
    """'2026-05-14' → 'Mi, 14. Mai'"""
    if not iso:
        return "–"
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{_WEEKDAYS_DE[d.weekday()]}, {d.day}. {_MONTHS_DE[d.month]}"
    except Exception:
        return str(iso)


def fmt_duration(minutes: Optional[int]) -> str:
    if not minutes:
        return "–"
    h, m = divmod(minutes, 60)
    return f"{h}h {m}min" if h else f"{m}min"


def fmt_sleep(minutes: Optional[int]) -> str:
    """Schlafdauer als '7h 12min' ohne 'Minuten'-Wort."""
    return fmt_duration(minutes)


def _step_source_label(source: Optional[str]) -> str:
    if source == "google_fit":
        return "Handy"
    if source == "garmin":
        return "Garmin"
    return ""


def fmt_steps(steps: int, source: Optional[str]) -> str:
    label = _step_source_label(source)
    src = f" ({label})" if label and source != "garmin" else ""
    return f"{steps:,}{src}".replace(",", ".")


def fmt_delta(delta: Optional[float], unit: str = "") -> str:
    if delta is None:
        return "–"
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta}{unit}"


def fmt_score(score: Optional[int]) -> str:
    if score is None:
        return "–"
    if score >= 85:
        icon = "✅"
    elif score >= 70:
        icon = "🟢"
    elif score >= 55:
        icon = "⚠️"
    else:
        icon = "🔴"
    return f"{icon} {score}/100"


def _score_icon(score: Optional[int]) -> str:
    if score is None:
        return "⚪"
    if score >= 85:
        return "✅"
    if score >= 70:
        return "🟢"
    if score >= 55:
        return "⚠️"
    return "🔴"


def fmt_hrv_status(status: Optional[str]) -> str:
    mapping = {
        "BALANCED": "🟢 Ausgeglichen",
        "UNBALANCED": "🟡 Unausgeglichen",
        "POOR": "🔴 Schlecht",
        "GOOD": "🟢 Gut",
    }
    return mapping.get((status or "").upper(), status or "–")


def _coach_block(text: Optional[str], title: str = "🧠 *Coach*", max_lines: int = 6) -> list[str]:
    if not text or not text.strip():
        return []
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    spaced_lines = []
    for line in lines[:max_lines]:
        spaced_lines.extend([line, ""])
    return [title, *spaced_lines]


def _num(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _outlier_bullets(snapshot: dict) -> list[str]:
    """Liefert 0-3 Bullets für Werte, die heute auffällig vs. Baseline sind."""
    bullets = []

    hrv = _num(snapshot.get("avg_hrv"))
    hrv_weekly = _num(snapshot.get("hrv_weekly_avg"))
    if hrv is not None and hrv_weekly is not None and hrv_weekly > 0:
        delta = round(hrv - hrv_weekly)
        if abs(delta) >= 5:
            arrow = "📈" if delta > 0 else "📉"
            bullets.append(f"{arrow} HRV {fmt_delta(delta, ' ms')} vs. 7T-Schnitt ({int(hrv_weekly)} ms)")

    readiness = snapshot.get("readiness") or {}
    sleep_debt = readiness.get("sleep_debt_minutes") or 0
    if sleep_debt >= 30:
        bullets.append(f"🧾 Schlafschuld: {fmt_duration(sleep_debt)}")

    bb = _num(snapshot.get("body_battery"))
    if bb is not None and bb < 30:
        bullets.append(f"🪫 Body Battery niedrig: {int(bb)}/100")

    stress = _num(snapshot.get("avg_stress"))
    if stress is not None and stress >= 50:
        bullets.append(f"😤 Stress erhöht: {int(stress)}")

    return bullets[:3]


def _gfit_footer(snapshot: dict) -> list[str]:
    """Re-Auth-Warnung oder dezenter Hinweis dass Google Fit als Quelle verwendet wurde."""
    status = snapshot.get("gfit_status")
    source = snapshot.get("steps_source")
    garmin_raw = snapshot.get("garmin_steps_raw") or 0

    lines = []

    if status == "auth_expired" and garmin_raw < 500:
        lines.append(
            "⚠️ Google Fit muss neu autorisiert werden — Token abgelaufen.\n"
            "    → `google_fit_token.json` mit `GOOGLE_FIT_INTERACTIVE_AUTH=1` erneuern."
        )
    elif source == "google_fit" and garmin_raw < 500:
        lines.append("ℹ️ Garmin heute nicht getragen — Schritte aus Google Fit (Handy).")

    return lines


def morning_briefing(snapshot: dict, coach_text: Optional[str] = None) -> str:
    sleep = fmt_sleep(snapshot.get("sleep_duration_minutes"))
    deep = fmt_sleep(snapshot.get("deep_sleep_minutes"))
    rem = fmt_sleep(snapshot.get("rem_sleep_minutes"))
    readiness = snapshot.get("readiness") or {}
    score = readiness.get("score")

    header = (
        f"☀️ *{fmt_date_short(snapshot.get('date'))}* · "
        f"{_score_icon(score)} *{readiness.get('recommendation', '–')}* · "
        f"{score if score is not None else '–'}/100"
    )

    lines = [header, ""]
    lines.extend(_coach_block(coach_text, max_lines=4))
    lines.append("📊 *Kurzlage*")
    lines.append(
        f"💤 {sleep} · Score {snapshot.get('sleep_score', '–')} · "
        f"Tief {deep} · REM {rem}"
    )
    lines.append(
        f"❤️ HRV {snapshot.get('avg_hrv', '–')} ms {fmt_hrv_status(snapshot.get('hrv_status'))} · "
        f"🔋 BB {snapshot.get('body_battery', '–')}/100 · "
        f"💓 RHR {snapshot.get('resting_hr', '–')} bpm"
    )

    outliers = _outlier_bullets(snapshot)
    if outliers:
        lines.append("")
        lines.append("⚡ *Heute auffällig*")
        for o in outliers:
            lines.append(f"• {o}")

    footer = _gfit_footer(snapshot)
    if footer:
        lines.append("")
        lines.extend(footer)

    return "\n".join(lines)


def evening_summary(snapshot: dict, activities: list, coach_text: Optional[str] = None) -> str:
    steps_value = snapshot.get("steps", 0) or 0
    steps = fmt_steps(steps_value, snapshot.get("steps_source", ""))
    step_goal_hit = "✅" if steps_value >= 10000 else "⏳"

    lines = [
        f"🌙 *Tagesabschluss — {fmt_date_short(snapshot.get('date'))}*",
        "",
    ]
    lines.extend(_coach_block(coach_text, max_lines=4))

    if activities:
        lines.append("🏋️ *Heute trainiert*")
        for a in activities:
            dist = f" · {a.get('distance_km')} km" if a.get("distance_km") else ""
            lines.append(f"• {a.get('name', a.get('type', '?'))} — {fmt_duration(a.get('duration_minutes'))}{dist}")
        lines.append("")

    lines.append("📊 *Heute*")
    lines.append(f"👣 {steps} · Ziel {step_goal_hit}")
    lines.append(
        f"⚡ Aktiv {snapshot.get('active_minutes', 0)} min · "
        f"🔥 {snapshot.get('calories', 0)} kcal"
    )
    lines.append(
        f"😤 Stress {snapshot.get('avg_stress', '–')} · "
        f"🔋 BB {snapshot.get('body_battery', '–')}/100"
    )

    footer = _gfit_footer(snapshot)
    if footer:
        lines.append("")
        lines.extend(footer)

    return "\n".join(lines)


def weekly_summary(weekly: dict, coach_text: Optional[str] = None) -> str:
    gym = weekly.get("gym_days", 0)
    cardio = weekly.get("cardio_days", 0)
    gym_goal = weekly.get("gym_goal", 3)
    cardio_goal = weekly.get("cardio_goal", 3)
    gym_icon = "✅" if gym >= gym_goal else "⚠️"
    cardio_icon = "✅" if cardio >= cardio_goal else "⚠️"
    trend = weekly.get("training_trend") or {}
    load = weekly.get("total_load", 0)
    load_status = trend.get("load_status", "–")

    lead = (
        f"📅 *Woche {fmt_date_short(weekly.get('week_start'))} – {fmt_date_short(weekly.get('week_end'))}*\n"
        f"{gym_icon} Gym {gym}/{gym_goal} · {cardio_icon} Cardio {cardio}/{cardio_goal} · "
        f"📈 Load {load} ({load_status})"
    )

    lines = [lead, ""]
    lines.extend(_coach_block(coach_text, title="🧠 *Wochenfazit*", max_lines=6))

    lines.append("📊 *Training Load*")
    lines.append(
        f"📏 {weekly.get('total_distance_km', 0)} km · "
        f"⏱ {fmt_duration(weekly.get('total_duration_minutes'))} · "
        f"🔥 {weekly.get('total_calories_burned', 0)} kcal"
    )
    lines.append(
        f"🧭 Fitness/Fatigue/Form: {trend.get('fitness', 0)} / {trend.get('fatigue', 0)} / {trend.get('form', 0)} · "
        f"Prognose Woche: {trend.get('projected_weekly_load', 0)}"
    )

    lines.append("")
    lines.append("💤 *Schlaf (Ø)*")
    lines.append(
        f"{fmt_sleep(weekly.get('avg_sleep_minutes'))} · Score {weekly.get('avg_sleep_score', '–')} · "
        f"Tief {fmt_sleep(weekly.get('avg_deep_sleep_minutes'))} · "
        f"REM {fmt_sleep(weekly.get('avg_rem_sleep_minutes'))}"
    )

    lines.append("")
    lines.append("🫀 *Erholung (heute)*")
    lines.append(
        f"HRV {weekly.get('today_hrv', '–')} ms · "
        f"BB {weekly.get('today_body_battery', '–')} · "
        f"RHR {weekly.get('today_resting_hr', '–')} bpm"
    )

    if weekly.get("weight_available"):
        lines.append("")
        lines.append("⚖️ *Körperkomposition (30T)*")
        lines.append(
            f"{weekly.get('latest_weight')} kg ({fmt_delta(weekly.get('weight_delta'), ' kg')}) · "
            f"KF {weekly.get('latest_body_fat')} % ({fmt_delta(weekly.get('fat_delta'), ' %')}) · "
            f"Muskel {weekly.get('latest_muscle_mass')} kg ({fmt_delta(weekly.get('muscle_delta'), ' kg')})"
        )
        lines.append(
            f"Unterhautfett {weekly.get('latest_subfat', '–')} % · "
            f"Viszeral {weekly.get('latest_visceral_fat', '–')} · "
            f"Protein {weekly.get('latest_protein', '–')} % · "
            f"Körperalter {weekly.get('latest_metabolic_age', '–')}"
        )
    else:
        lines.append("")
        lines.append("⚖️ Keine Renpho-Daten — bitte wiegen!")

    snapshot = weekly.get("snapshot") or {}
    footer = _gfit_footer(snapshot)
    if footer:
        lines.append("")
        lines.extend(footer)

    return "\n".join(lines)


def training_plan(plan: dict, coach_text: Optional[str] = None) -> str:
    snapshot = plan.get("snapshot") or {}
    weekly = plan.get("weekly") or {}
    readiness = plan.get("readiness") or snapshot.get("readiness") or {}
    trend = weekly.get("training_trend") or {}
    factors = readiness.get("limiting_factors") or ["keine starken Limitierungen"]
    factor_text = "\n".join(f"• {factor}" for factor in factors[:3])

    return (
        f"🎯 *Trainingsplan heute*\n\n"
        f"{fmt_score(readiness.get('score'))} *{readiness.get('recommendation', '–')}*\n"
        f"🏋️ Vorschlag: {plan.get('suggested_session', '–')}\n\n"
        f"{chr(10).join(_coach_block(coach_text, max_lines=4))}"
        f"📌 *Warum:*\n{factor_text}\n\n"
        f"📊 *Woche:* Gym {weekly.get('gym_days', 0)}/{weekly.get('gym_goal', 3)} · "
        f"Cardio {weekly.get('cardio_days', 0)}/{weekly.get('cardio_goal', 3)}\n"
        f"🔥 Load: {weekly.get('total_load', 0)} · Form: {trend.get('form', 0)}\n"
        f"🧪 {readiness.get('calibration', '–')}"
    )


def weight_summary(trend: dict, coach_text: Optional[str] = None) -> str:
    if not trend.get("available"):
        return "⚖️ Keine Renpho-Daten vorhanden.\nBitte wiege dich für bessere Insights!"

    def _v(val, unit="", fallback="–"):
        return f"{val}{unit}" if val is not None else fallback

    lines = [
        f"⚖️ *Körperkomposition* (letzte {trend.get('period_days')} Tage)\n",
        *_coach_block(coach_text, title="🧠 *Einordnung*", max_lines=5),
        f"🏋️ Gewicht: *{_v(trend.get('latest_weight'), ' kg')}* ({fmt_delta(trend.get('weight_delta'), ' kg')})",
        f"📉 7T-Schnitt: {_v(trend.get('avg_weight_7d'), ' kg')} · pro Woche: {fmt_delta(trend.get('weight_delta_per_week'), ' kg')}",
        f"📊 BMI: {_v(trend.get('latest_bmi'))}",
        "",
        f"🔬 *Körperfett & Masse:*",
        f"  Körperfett gesamt: {_v(trend.get('latest_body_fat'), ' %')} ({fmt_delta(trend.get('fat_delta'), ' %')})",
        f"  Unterhautfett: {_v(trend.get('latest_subfat'), ' %')}",
        f"  Viszeralfett Level: {_v(trend.get('latest_visceral_fat'))}",
        "",
        f"💪 *Muskeln & Lean Mass:*",
        f"  Muskelmasse: {_v(trend.get('latest_muscle_mass'), ' kg')} ({fmt_delta(trend.get('muscle_delta'), ' kg')})",
        f"  Fettfreie Masse: {_v(trend.get('latest_lean_mass'), ' kg')}",
        f"  Fettfreies Gewicht: {_v(trend.get('latest_fat_free_weight'), ' kg')}",
        "",
        f"💧 *Weitere Werte:*",
        f"  Körperwasser: {_v(trend.get('latest_body_water'), ' %')}",
        f"  Protein: {_v(trend.get('latest_protein'), ' %')}",
        f"  Knochenmasse: {_v(trend.get('latest_bone_mass'), ' kg')}",
        f"  Grundumsatz (BMR): {_v(trend.get('latest_bmr'), ' kcal')}",
        f"  Körperalter: {_v(trend.get('latest_metabolic_age'), ' Jahre')}",
        "",
        f"📏 {trend.get('measurements_count')} Messungen in {trend.get('period_days')} Tagen",
        f"Messqualität: {trend.get('measurement_quality', '–')} ({trend.get('measurement_density_per_week', 0)}/Woche)",
        f"Letzte Messung: {fmt_date(trend.get('latest_date'))}",
    ]
    return "\n".join(lines)


def recovery_summary(snapshot: dict) -> str:
    return (
        f"🔄 *Erholungsstatus — {fmt_date(snapshot.get('date'))}*\n\n"
        f"❤️ *HRV:* {snapshot.get('avg_hrv', '–')} ms "
        f"(Ø Woche: {snapshot.get('hrv_weekly_avg', '–')} ms)\n"
        f"   Status: {fmt_hrv_status(snapshot.get('hrv_status'))}\n\n"
        f"🔋 *Body Battery:* {snapshot.get('body_battery', '–')}/100\n"
        f"💓 *Ruhe-Puls:* {snapshot.get('resting_hr', '–')} bpm\n"
        f"😓 *Stress:* {snapshot.get('avg_stress', '–')}"
    )


_ZONE_COLORS = {1: "🔵", 2: "🟢", 3: "🟡", 4: "🟠", 5: "🔴"}


def fmt_hr_zones(zones: list) -> str:
    if not zones:
        return ""
    parts = [
        f"{_ZONE_COLORS.get(z['zone'], '⚪')}Z{z['zone']}: {z['pct']}%"
        for z in zones if z.get("pct", 0) > 0
    ]
    return "  " + " · ".join(parts) if parts else ""


def activity_list(activities: list) -> str:
    if not activities:
        return "Keine Aktivitäten gefunden."
    lines = ["🏆 *Letzte Aktivitäten:*\n"]
    for a in activities:
        atype = (a.get("type") or "").lower()
        is_run = any(t in atype for t in ("running", "trail", "treadmill"))

        dist = f" · {a.get('distance_km')} km" if a.get("distance_km") else ""
        hr = f" · ❤️ {a.get('avg_hr')} bpm" if a.get("avg_hr") else ""
        cal = f" · 🔥 {a.get('calories')} kcal" if a.get("calories") else ""
        load = f" · Load {a.get('load')} ({a.get('load_label')})" if a.get("load") is not None else ""

        line = (
            f"• *{a.get('name', a.get('type', '?'))}*\n"
            f"  📅 {fmt_date(a.get('start_time', '')[:10])} · ⏳ {fmt_duration(a.get('duration_minutes'))}"
            f"{dist}{hr}{cal}{load}"
        )

        if is_run:
            pace = f"⏱ {a.get('avg_pace_min_km')} /km" if a.get("avg_pace_min_km") else ""
            spm = f"👟 {int(a.get('avg_spm'))} spm" if a.get("avg_spm") else ""
            gct = f"🦶 {int(a.get('avg_ground_contact_ms'))} ms" if a.get("avg_ground_contact_ms") else ""
            vo = f"↕️ {a.get('avg_vertical_oscillation_cm')} cm" if a.get("avg_vertical_oscillation_cm") else ""
            vr = f"📐 {a.get('avg_vertical_ratio_pct')}%" if a.get("avg_vertical_ratio_pct") else ""
            elev = f"⛰ +{a.get('elevation_gain_m')} m" if a.get("elevation_gain_m") else ""
            run_stats = " · ".join(x for x in [pace, spm, gct, vo, vr, elev] if x)
            if run_stats:
                line += f"\n  {run_stats}"

        # Training Effect
        te_a = a.get("training_effect_aerobic")
        te_an = a.get("training_effect_anaerobic")
        if te_a or te_an:
            line += f"\n  💪 TE aerob: {te_a or '–'} · anaerob: {te_an or '–'}"

        # HR-Zonen
        zones_str = fmt_hr_zones(a.get("hr_zones") or [])
        if zones_str:
            line += f"\n{zones_str}"

        lines.append(line)
    return "\n".join(lines)


def renpho_reminder(days_since: int) -> str:
    return (
        f"⚖️ *Renpho-Erinnerung*\n\n"
        f"Du hast dich seit {days_since} Tagen nicht gewogen.\n"
        f"Für genaue Körperkompositions-Insights — jetzt wiegen! 💪"
    )


def gfit_auth_warning(detail: Optional[str] = None) -> str:
    base = (
        "⚠️ *Google Fit Auth abgelaufen*\n\n"
        "Der Bot kann aktuell keine Schritte vom Google-Fit-Konto abrufen. "
        "Wenn du die Garmin nicht trägst, fehlen heute die Schritte.\n\n"
        "*Fix:* `google_fit_token.json` mit `GOOGLE_FIT_INTERACTIVE_AUTH=1` neu autorisieren."
    )
    if detail:
        base += f"\n\n_Detail:_ {detail}"
    return base
