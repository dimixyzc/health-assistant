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


def fmt_date(iso: Optional[str]) -> str:
    """'2026-05-14' → '14. Mai 2026'"""
    if not iso:
        return "–"
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{d.day}. {_MONTHS_DE[d.month]} {d.year}"
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


def fmt_steps(steps: int, source: str) -> str:
    src = " (Google Fit)" if source == "google_fit" else ""
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


def fmt_hrv_status(status: Optional[str]) -> str:
    mapping = {
        "BALANCED": "🟢 Ausgeglichen",
        "UNBALANCED": "🟡 Unausgeglichen",
        "POOR": "🔴 Schlecht",
        "GOOD": "🟢 Gut",
    }
    return mapping.get((status or "").upper(), status or "–")


def _coach_block(text: Optional[str], title: str = "🧠 *Coach*") -> list[str]:
    if not text or not text.strip():
        return []
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return [title, *lines[:3], ""]


def morning_briefing(snapshot: dict, coach_text: Optional[str] = None) -> str:
    sleep = fmt_sleep(snapshot.get("sleep_duration_minutes"))
    deep = fmt_sleep(snapshot.get("deep_sleep_minutes"))
    rem = fmt_sleep(snapshot.get("rem_sleep_minutes"))
    readiness = snapshot.get("readiness") or {}
    sleep_debt = readiness.get("sleep_debt_minutes")
    lines = [
        f"☀️ *Guten Morgen — {fmt_date(snapshot.get('date'))}*\n\n"
        f"🎯 *{readiness.get('recommendation', '–')}* · {fmt_score(readiness.get('score'))}",
        "",
        *_coach_block(coach_text),
        "📊 *Kurzlage*",
        f"💤 Schlaf: {sleep} · Score {snapshot.get('sleep_score', '–')} · Tief {deep} · REM {rem}",
        f"❤️ *HRV:* {snapshot.get('avg_hrv', '–')} ms — {fmt_hrv_status(snapshot.get('hrv_status'))}\n"
        f"🔋 *Body Battery:* {snapshot.get('body_battery', '–')}/100\n"
        f"💓 *Ruhe-Puls:* {snapshot.get('resting_hr', '–')} bpm",
    ]
    if sleep_debt:
        lines.append(f"🧾 Schlafschuld: {fmt_duration(sleep_debt)}")
    return "\n".join(lines)


def evening_summary(snapshot: dict, activities: list, coach_text: Optional[str] = None) -> str:
    steps = fmt_steps(snapshot.get("steps", 0), snapshot.get("steps_source", ""))
    lines = [
        f"🌙 *Tagesabschluss*\n",
        *_coach_block(coach_text),
        f"📊 *Heute*",
        f"👣 Schritte: {steps}",
        f"⚡ Aktive Minuten: {snapshot.get('active_minutes', 0)}",
        f"🔥 Kalorien: {snapshot.get('calories', 0)} kcal",
        f"😤 Stress-Level: {snapshot.get('avg_stress', '–')}",
        f"🔋 Body Battery: {snapshot.get('body_battery', '–')}/100",
    ]
    if activities:
        lines.append("\n🏋️ *Aktivitäten heute:*")
        for a in activities:
            dist = f" · {a.get('distance_km')} km" if a.get("distance_km") else ""
            lines.append(f"  • {a.get('name', a.get('type', '?'))} — {fmt_duration(a.get('duration_minutes'))}{dist}")
    return "\n".join(lines)


def weekly_summary(weekly: dict, coach_text: Optional[str] = None) -> str:
    gym = weekly.get("gym_days", 0)
    run = weekly.get("run_days", 0)
    gym_goal = weekly.get("gym_goal", 3)
    run_goal = weekly.get("run_goal", 3)
    gym_icon = "✅" if gym >= gym_goal else "⚠️"
    run_icon = "✅" if run >= run_goal else "⚠️"
    trend = weekly.get("training_trend") or {}

    lines = [
        f"📅 *Woche {fmt_date(weekly.get('week_start'))} – {fmt_date(weekly.get('week_end'))}*\n",
        *_coach_block(coach_text, title="🧠 *Wochenfazit*"),
        f"🏋️ *Ziele*",
        f"{gym_icon} Gym: {gym}/{gym_goal} Einheiten · offen: {weekly.get('gym_remaining', 0)}",
        f"{run_icon} Laufen: {run}/{run_goal} Einheiten · offen: {weekly.get('run_remaining', 0)}",
        "",
        f"📊 *Training Load*",
        f"📏 Gesamtdistanz: {weekly.get('total_distance_km', 0)} km",
        f"⏱ Trainingsdauer: {fmt_duration(weekly.get('total_duration_minutes'))}",
        f"🔥 Kalorien: {weekly.get('total_calories_burned', 0)} kcal",
        f"📈 Load: {weekly.get('total_load', 0)} · Prognose: {trend.get('projected_weekly_load', 0)} ({trend.get('load_status', '–')})",
        f"🧭 Fitness/Fatigue/Form: {trend.get('fitness', 0)} / {trend.get('fatigue', 0)} / {trend.get('form', 0)}\n",
        f"💤 *Schlaf (Ø)*",
        f"Dauer: {fmt_sleep(weekly.get('avg_sleep_minutes'))} | Score: {weekly.get('avg_sleep_score', '–')}",
        f"Tief: {fmt_sleep(weekly.get('avg_deep_sleep_minutes'))} · REM: {fmt_sleep(weekly.get('avg_rem_sleep_minutes'))}\n",
        f"🫀 *Erholung (heute)*",
        f"HRV: {weekly.get('today_hrv', '–')} ms · "
        f"Body Battery: {weekly.get('today_body_battery', '–')} · "
        f"Ruhe-Puls: {weekly.get('today_resting_hr', '–')} bpm",
    ]

    if weekly.get("weight_available"):
        lines += [
            f"\n⚖️ *Körperkomposition (30-Tage-Trend)*",
            f"Gewicht: {weekly.get('latest_weight')} kg ({fmt_delta(weekly.get('weight_delta'), ' kg')})",
            f"Körperfett: {weekly.get('latest_body_fat')} % ({fmt_delta(weekly.get('fat_delta'), ' %')}) · "
            f"Unterhautfett: {weekly.get('latest_subfat', '–')} %",
            f"Muskelmasse: {weekly.get('latest_muscle_mass')} kg ({fmt_delta(weekly.get('muscle_delta'), ' kg')})",
            f"Viszeralfett Level: {weekly.get('latest_visceral_fat', '–')} · "
            f"Protein: {weekly.get('latest_protein', '–')} % · "
            f"Körperalter: {weekly.get('latest_metabolic_age', '–')} Jahre",
        ]
    else:
        lines.append("\n⚖️ Keine Renpho-Daten — bitte wiegen!")

    return "\n".join(lines)


def training_plan(plan: dict) -> str:
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
        f"📌 *Warum:*\n{factor_text}\n\n"
        f"📊 *Woche:* Gym {weekly.get('gym_days', 0)}/{weekly.get('gym_goal', 3)} · "
        f"Laufen {weekly.get('run_days', 0)}/{weekly.get('run_goal', 3)}\n"
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
        *_coach_block(coach_text, title="🧠 *Einordnung*"),
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
