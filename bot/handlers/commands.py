import logging
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from analytics import formatter, insights, metrics
from ai.openai_client import OpenAIHealthAssistant
from connectors import garmin as garmin_conn
from storage import database as db
from config import settings

logger = logging.getLogger(__name__)
router = Router()

_ai: OpenAIHealthAssistant | None = None


def get_ai() -> OpenAIHealthAssistant:
    global _ai
    if _ai is None:
        _ai = OpenAIHealthAssistant(settings.openai_api_key, settings.openai_model)
    return _ai


def _authorized(message: Message) -> bool:
    return message.chat.id == settings.telegram_chat_id


def _asks_for_hrv_trend(text: str | None) -> bool:
    if not text:
        return False
    normalized = text.lower()
    trend_terms = ("entwicklung", "trend", "verlauf", "entwickelt", "verändert")
    hrv_terms = ("hrv", "herzratenvariabil")
    return any(term in normalized for term in hrv_terms) and any(term in normalized for term in trend_terms)


def _command_payload(text: str | None) -> str:
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _extract_score(payload: str, *names: str) -> int | None:
    aliases = "|".join(re.escape(name) for name in names)
    match = re.search(rf"(?:^|\s)(?:{aliases})\s*[:=]\s*(10|[1-9])(?:\s|$)", payload, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _extract_text_value(payload: str, *names: str) -> str | None:
    aliases = "|".join(re.escape(name) for name in names)
    match = re.search(rf"(?:^|\s)(?:{aliases})\s*[:=]\s*([^\s|;\n]+)", payload, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip() or None


def _strip_key_values(payload: str) -> str:
    cleaned = re.sub(r"(?:^|\s)\w+\s*[:=]\s*[^\s|;\n]+", " ", payload)
    return re.sub(r"\s+", " ", cleaned).strip() or None


def _parse_journal_payload(payload: str) -> dict:
    return {
        "mood": _extract_score(payload, "stimmung", "mood"),
        "energy": _extract_score(payload, "energie", "energy"),
        "stress": _extract_score(payload, "stress"),
        "sleep_quality": _extract_score(payload, "schlaf", "sleep", "sleep_quality"),
        "soreness": _extract_score(payload, "kater", "muskelkater", "soreness"),
        "symptoms": _extract_text_value(payload, "symptome", "symptoms"),
        "tags": _extract_text_value(payload, "tags", "tag"),
        "note": _strip_key_values(payload),
    }


@router.message(Command("start", "hilfe", "help"))
async def cmd_start(message: Message) -> None:
    if not _authorized(message):
        return
    text = (
        "👋 *Hallo Dimitri!*\n\n"
        "Ich bin dein persönlicher Fitness-Assistent. Hier sind meine Befehle:\n\n"
        "/heute — Tages-Snapshot (Schlaf, Schritte, Body Battery)\n"
        "/plan — Konkrete Trainingsempfehlung für heute\n"
        "/erholung — HRV, Body Battery, Training Readiness\n"
        "/training — Letzte Aktivitäten\n"
        "/woche — Wöchentliche Zusammenfassung\n"
        "/gewicht — Renpho Körperkomposition & Trend\n"
        "/journal — Tages-Check-in speichern\n"
        "/journal_review — Journal-Muster anzeigen\n"
        "/experiment_start — 14-Tage-Experiment starten\n"
        "/experimente — Aktive Experimente\n"
        "/tipps — Personalisierter Trainingstipp\n"
        "/status — Schnellübersicht"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("heute"))
async def cmd_heute(message: Message) -> None:
    if not _authorized(message):
        return
    await message.answer("⏳ Hole Tagesdaten...")
    try:
        snapshot = await insights.get_daily_snapshot()
        activities = await garmin_conn.get_recent_activities(
            settings.garmin_email, settings.garmin_password, settings.data_dir, limit=3
        )
        today_activities = [
            a for a in activities
            if a.get("start_time", "").startswith(snapshot["date"])
        ]
        coach_text = await get_ai().generate_morning_briefing(snapshot)
        text = formatter.morning_briefing(snapshot, coach_text=coach_text)
        if today_activities:
            text += "\n\n" + formatter.activity_list(today_activities)
    except Exception as e:
        logger.error(f"/heute Fehler: {e}")
        snapshot = {}
        text = "⚠️ Fehler beim Laden der Tagesdaten."
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("erholung"))
async def cmd_erholung(message: Message) -> None:
    if not _authorized(message):
        return
    await message.answer("⏳ Hole Erholungsdaten...")
    try:
        snapshot = await insights.get_daily_snapshot()
        text = formatter.recovery_summary(snapshot)
    except Exception as e:
        logger.error(f"/erholung Fehler: {e}")
        text = "⚠️ Fehler beim Laden der Erholungsdaten."
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("training"))
async def cmd_training(message: Message) -> None:
    if not _authorized(message):
        return
    await message.answer("⏳ Hole Aktivitäten...")
    try:
        activities = await garmin_conn.get_recent_activities_with_zones(
            settings.garmin_email, settings.garmin_password, settings.data_dir, limit=5
        )
        activities = metrics.add_activity_loads(activities)
        text = formatter.activity_list(activities)
    except Exception as e:
        logger.error(f"/training Fehler: {e}")
        text = "⚠️ Fehler beim Laden der Aktivitäten."
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("woche"))
async def cmd_woche(message: Message) -> None:
    if not _authorized(message):
        return
    await message.answer("⏳ Erstelle Wochenanalyse...")
    try:
        weekly = await insights.get_weekly_summary()
        coach_text = await get_ai().generate_weekly_summary(weekly)
        text = formatter.weekly_summary(weekly, coach_text=coach_text)
    except Exception as e:
        logger.error(f"/woche Fehler: {e}")
        text = "⚠️ Fehler beim Laden der Wochendaten."
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("gewicht"))
async def cmd_gewicht(message: Message) -> None:
    if not _authorized(message):
        return
    await message.answer("⏳ Hole Renpho-Daten...")
    try:
        await insights.refresh_renpho_cache()
        trend = await insights.get_weight_trend(days=30)
        coach_text = await get_ai().generate_weight_insight(trend)
        text = formatter.weight_summary(trend, coach_text=coach_text)
    except Exception as e:
        logger.error(f"/gewicht Fehler: {e}")
        text = "⚠️ Fehler beim Laden der Körperdaten."
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("tipps"))
async def cmd_tipps(message: Message) -> None:
    if not _authorized(message):
        return
    await message.answer("⏳ Generiere Trainingstipp...")
    try:
        snapshot = await insights.get_daily_snapshot()
        activities = await garmin_conn.get_recent_activities(
            settings.garmin_email, settings.garmin_password, settings.data_dir, limit=5
        )
        text = await get_ai().generate_training_tip(snapshot, activities)
    except Exception as e:
        logger.error(f"/tipps Fehler: {e}")
        text = ""
    if not text or not text.strip():
        text = "⚠️ Tipp konnte nicht generiert werden. Bitte später erneut versuchen."
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("plan"))
async def cmd_plan(message: Message) -> None:
    if not _authorized(message):
        return
    await message.answer("⏳ Berechne Trainingsplan...")
    try:
        plan = await insights.get_training_plan()
        coach_text = await get_ai().generate_plan_explanation(plan)
        text = formatter.training_plan(plan, coach_text=coach_text)
    except Exception as e:
        logger.error(f"/plan Fehler: {e}")
        text = "⚠️ Trainingsplan konnte nicht berechnet werden."
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("journal", "checkin"))
async def cmd_journal(message: Message) -> None:
    if not _authorized(message):
        return
    payload = _command_payload(message.text)
    if not payload:
        await message.answer(formatter.journal_help(), parse_mode="Markdown")
        return
    try:
        entry = _parse_journal_payload(payload)
        saved = await db.upsert_journal_entry(settings.data_dir, entry)
        await message.answer(formatter.journal_saved(saved), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"/journal Fehler: {e}")
        await message.answer("⚠️ Journal konnte nicht gespeichert werden.", parse_mode="Markdown")


@router.message(Command("journal_review", "journal_heute"))
async def cmd_journal_review(message: Message) -> None:
    if not _authorized(message):
        return
    try:
        review = await insights.get_journal_review(days=14)
        await message.answer(formatter.journal_review(review), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"/journal_review Fehler: {e}")
        await message.answer("⚠️ Journal Review konnte nicht geladen werden.", parse_mode="Markdown")


@router.message(Command("experiment_start"))
async def cmd_experiment_start(message: Message) -> None:
    if not _authorized(message):
        return
    payload = _command_payload(message.text)
    if not payload:
        await message.answer(
            "🧪 Nutze: `/experiment_start Name | Hypothese | Zielmetrik`\n"
            "Beispiel: `/experiment_start Koffein vor 12 | besserer Schlaf | Schlafqualität`",
            parse_mode="Markdown",
        )
        return
    parts = [part.strip() for part in payload.split("|")]
    try:
        experiment = await db.create_experiment(settings.data_dir, {
            "name": parts[0],
            "hypothesis": parts[1] if len(parts) > 1 else None,
            "target_metric": parts[2] if len(parts) > 2 else None,
            "duration_days": 14,
        })
        await message.answer(formatter.experiment_created(experiment), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"/experiment_start Fehler: {e}")
        await message.answer("⚠️ Experiment konnte nicht gestartet werden.", parse_mode="Markdown")


@router.message(Command("experimente", "experiments"))
async def cmd_experimente(message: Message) -> None:
    if not _authorized(message):
        return
    try:
        experiments = await db.get_active_experiments(settings.data_dir)
        await message.answer(formatter.experiments_list(experiments), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"/experimente Fehler: {e}")
        await message.answer("⚠️ Experimente konnten nicht geladen werden.", parse_mode="Markdown")


@router.message(F.text & ~F.text.startswith("/"))
async def cmd_freitext(message: Message) -> None:
    """Beantwortet natürlichsprachige Fragen mit vollem Kontext."""
    if not _authorized(message):
        return
    await message.answer("⏳ Analysiere...")
    try:
        import asyncio
        base_tasks = [
            insights.get_daily_snapshot(),
            garmin_conn.get_recent_activities(
                settings.garmin_email, settings.garmin_password, settings.data_dir, limit=10
            ),
            insights.get_weight_trend(days=30),
        ]
        if _asks_for_hrv_trend(message.text):
            base_tasks.append(insights.get_hrv_trend(days=28))

        results = await asyncio.gather(*base_tasks, return_exceptions=True)
        snapshot, activities, weight_trend = results[:3]
        hrv_trend = results[3] if len(results) > 3 else None
        if isinstance(snapshot, Exception):
            snapshot = {}
        if isinstance(activities, Exception):
            activities = []
        if isinstance(weight_trend, Exception):
            weight_trend = {"available": False}
        if isinstance(hrv_trend, Exception):
            hrv_trend = {"available": False}
        text = await get_ai().answer_free_question(
            question=message.text,
            snapshot=snapshot,
            activities=activities,
            weight_trend=weight_trend,
            hrv_trend=hrv_trend,
        )
    except Exception as e:
        logger.error(f"Freitext-Fehler: {e}")
        text = ""
    if not text or not text.strip():
        text = "⚠️ Konnte die Frage nicht beantworten. Bitte anders formulieren."
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not _authorized(message):
        return
    try:
        snapshot = await insights.get_daily_snapshot()
        latest_weight = await db.get_latest_renpho(settings.data_dir)
        weight_str = f"{latest_weight['weight_kg']} kg" if latest_weight else "–"
        readiness = snapshot.get("readiness") or {}
        text = (
            f"⚡ *Schnellstatus*\n\n"
            f"🎯 Readiness: {formatter.fmt_score(readiness.get('score'))} — {readiness.get('recommendation', '–')}\n"
            f"🔋 Body Battery: {snapshot.get('body_battery', '–')}\n"
            f"❤️ HRV: {snapshot.get('avg_hrv', '–')} ms\n"
            f"💓 Ruhe-Puls: {snapshot.get('resting_hr', '–')} bpm\n"
            f"👣 Schritte: {formatter.fmt_steps(snapshot.get('steps', 0), snapshot.get('steps_source', ''))}\n"
            f"💤 Schlaf: {formatter.fmt_duration(snapshot.get('sleep_duration_minutes'))}\n"
            f"⚖️ Gewicht: {weight_str}"
        )
    except Exception as e:
        logger.error(f"/status Fehler: {e}")
        text = "⚠️ Fehler beim Laden des Status."
    await message.answer(text, parse_mode="Markdown")
