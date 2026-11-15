import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message

from analytics import formatter, insights, metrics
from bot.delivery import answer as _answer_markdown, progress, ReplyMiddleware
from ai.client_factory import build_ai_client
from ai.openai_client import OpenAIHealthAssistant
from connectors import garmin as garmin_conn
from connectors import renpho as renpho_conn
from storage import database as db
from config import settings

logger = logging.getLogger(__name__)
router = Router()
router.message.outer_middleware(ReplyMiddleware(settings.telegram_chat_id))

_ai: OpenAIHealthAssistant | None = None


def get_ai() -> OpenAIHealthAssistant:
    global _ai
    if _ai is None:
        _ai = build_ai_client()
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


@router.message(Command("start", "hilfe", "help"))
async def cmd_start(message: Message) -> None:
    if not _authorized(message):
        return
    text = (
        "👋 <b>Hallo Dimitri!</b>\n\n"
        "Ich bin dein persönlicher Gesundheitsassistent. Während deiner Knie-Reha "
        "sind Schritte und Training nur Kontext, keine Ziele.\n\n"
        "/heute — Tages-Snapshot (Schlaf, Erholung, Body Battery)\n"
        "/plan — Gesundheitsfokus für heute\n"
        "/erholung — HRV, Body Battery, Training Readiness\n"
        "/training — Letzte Aktivitäten\n"
        "/woche — Wöchentliche Zusammenfassung\n"
        "/gewicht — Renpho Körperkomposition & Trend\n"
        "/experiment_start — 14-Tage-Experiment starten\n"
        "/experimente — Aktive Experimente\n"
        "/tipps — Personalisierter Gesundheitstipp\n"
        "/status — Schnellübersicht (ohne KI)\n"
        "/wissen — Buchquelle und Modell"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("wissen"))
async def cmd_wissen(message: Message) -> None:
    if not _authorized(message):
        return
    status = get_ai().knowledge_status()
    book = (
        f"📚 {status['title']} · {status['sections']} Abschnitte geladen."
        if status["available"] else
        "📚 Buch nicht geladen. EPUB unter /share/health-assistant/huberman_protocols.epub ablegen."
    )
    await message.answer(
        f"{book}\n🤖 Modell: {settings.openai_model}\n"
        "🔎 Passende Buchstellen plus CDC-/WHO-/NIH-Hinweise; keine Live-Literatursuche. "
        "Dein Behandlungsplan hat Vorrang.",
        parse_mode=None,
    )


@router.message(Command("heute"))
async def cmd_heute(message: Message) -> None:
    if not _authorized(message):
        return
    await progress(message, "⏳ Hole Tagesdaten...")
    try:
        snapshot = await insights.get_daily_snapshot()
        garmin_warning = ""
        try:
            activities = await garmin_conn.get_recent_activities(
                settings.garmin_email, settings.garmin_password, settings.data_dir, limit=3
            )
        except garmin_conn.GarminUnavailableError as e:
            activities = []
            garmin_warning = f"\n\n⚠️ {e}"
        today_activities = [
            a for a in activities
            if a.get("start_time", "").startswith(snapshot["date"])
        ]
        coach_text = await get_ai().generate_morning_briefing(snapshot)
        text = formatter.morning_briefing(snapshot, coach_text=coach_text)
        if today_activities:
            text += "\n\n" + formatter.activity_list(today_activities)
        text += garmin_warning
    except Exception as e:
        logger.error("/heute Fehler: %s", type(e).__name__)
        snapshot = {}
        text = "⚠️ Fehler beim Laden der Tagesdaten."
    await _answer_markdown(message, text)


@router.message(Command("erholung"))
async def cmd_erholung(message: Message) -> None:
    if not _authorized(message):
        return
    await progress(message, "⏳ Hole Erholungsdaten...")
    try:
        snapshot = await insights.get_daily_snapshot()
        text = formatter.recovery_summary(snapshot)
    except Exception as e:
        logger.error("/erholung Fehler: %s", type(e).__name__)
        text = "⚠️ Fehler beim Laden der Erholungsdaten."
    await _answer_markdown(message, text)


@router.message(Command("training"))
async def cmd_training(message: Message) -> None:
    if not _authorized(message):
        return
    await progress(message, "⏳ Hole Aktivitäten...")
    try:
        activities = await garmin_conn.get_recent_activities_with_zones(
            settings.garmin_email, settings.garmin_password, settings.data_dir, limit=5
        )
        activities = metrics.add_activity_loads(activities)
        text = formatter.activity_list(activities)
    except Exception as e:
        logger.error("/training Fehler: %s", type(e).__name__)
        text = "⚠️ Fehler beim Laden der Aktivitäten."
    await _answer_markdown(message, text)


@router.message(Command("woche"))
async def cmd_woche(message: Message) -> None:
    if not _authorized(message):
        return
    await progress(message, "⏳ Erstelle Wochenanalyse...")
    try:
        weekly = await insights.get_weekly_summary()
        coach_text = await get_ai().generate_weekly_summary(weekly)
        text = formatter.weekly_summary(weekly, coach_text=coach_text)
    except Exception as e:
        logger.error("/woche Fehler: %s", type(e).__name__)
        text = "⚠️ Fehler beim Laden der Wochendaten."
    await _answer_markdown(message, text)


@router.message(Command("gewicht"))
async def cmd_gewicht(message: Message) -> None:
    if not _authorized(message):
        return
    await progress(message, "⏳ Hole Renpho-Daten...")
    try:
        await insights.refresh_renpho_cache()
        trend = await insights.get_weight_trend(days=30)
        coach_text = await get_ai().generate_weight_insight(trend)
        text = formatter.weight_summary(trend, coach_text=coach_text)
    except renpho_conn.RenphoFetchError as e:
        logger.error("/gewicht Renpho-Fehler: %s", type(e).__name__)
        text = (
            "⚠️ Renpho-Daten konnten nicht abgerufen werden.\n"
            "Bitte prüfe E-Mail und Passwort in der Add-on-Konfiguration und starte das Add-on neu."
        )
    except Exception as e:
        logger.error("/gewicht Fehler: %s", type(e).__name__)
        text = "⚠️ Fehler beim Laden der Körperdaten."
    await _answer_markdown(message, text)


@router.message(Command("tipps"))
async def cmd_tipps(message: Message) -> None:
    if not _authorized(message):
        return
    await progress(message, "⏳ Generiere Gesundheitstipp...")
    try:
        snapshot = await insights.get_daily_snapshot()
        activities = await garmin_conn.get_recent_activities(
            settings.garmin_email, settings.garmin_password, settings.data_dir, limit=5
        )
        text = await get_ai().generate_training_tip(snapshot, activities)
    except Exception as e:
        logger.error("/tipps Fehler: %s", type(e).__name__)
        text = ""
    if not text or not text.strip():
        text = "⚠️ Tipp konnte nicht generiert werden. Bitte später erneut versuchen."
    await _answer_markdown(message, text)


@router.message(Command("plan"))
async def cmd_plan(message: Message) -> None:
    if not _authorized(message):
        return
    await progress(message, "⏳ Erstelle Gesundheitsfokus...")
    try:
        plan = await insights.get_training_plan()
        coach_text = await get_ai().generate_plan_explanation(plan)
        text = formatter.training_plan(plan, coach_text=coach_text)
    except Exception as e:
        logger.error("/plan Fehler: %s", type(e).__name__)
        text = "⚠️ Gesundheitsfokus konnte nicht berechnet werden."
    await _answer_markdown(message, text)


@router.message(Command("experiment_start"))
async def cmd_experiment_start(message: Message) -> None:
    if not _authorized(message):
        return
    payload = _command_payload(message.text)
    if not payload:
        await _answer_markdown(
            message, "🧪 Nutze: `/experiment_start Name | Hypothese | Zielmetrik`\n"
            "Beispiel: `/experiment_start Koffein vor 12 | besserer Schlaf | Schlafqualität`",
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
        await _answer_markdown(message, formatter.experiment_created(experiment))
    except Exception as e:
        logger.error("/experiment_start Fehler: %s", type(e).__name__)
        await _answer_markdown(message, "⚠️ Experiment konnte nicht gestartet werden.")


@router.message(Command("experimente", "experiments"))
async def cmd_experimente(message: Message) -> None:
    if not _authorized(message):
        return
    try:
        experiments = await db.get_active_experiments(settings.data_dir)
        await _answer_markdown(message, formatter.experiments_list(experiments))
    except Exception as e:
        logger.error("/experimente Fehler: %s", type(e).__name__)
        await _answer_markdown(message, "⚠️ Experimente konnten nicht geladen werden.")


@router.message(F.text & ~F.text.startswith("/"))
async def cmd_freitext(message: Message) -> None:
    """Beantwortet natürlichsprachige Fragen mit vollem Kontext."""
    if not _authorized(message):
        return
    await progress(message, "⏳ Analysiere...")
    try:
        base_tasks = [
            insights.get_daily_snapshot(),
            garmin_conn.get_recent_activities(
                settings.garmin_email, settings.garmin_password, settings.data_dir, limit=10
            ),
            insights.get_weight_trend(days=30),
        ]
        if _asks_for_hrv_trend(message.text):
            base_tasks.append(insights.get_hrv_trend(days=28))

        results = await asyncio.gather(
            *(asyncio.wait_for(task, timeout=25) for task in base_tasks),
            return_exceptions=True,
        )
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
        logger.error("Freitext-Fehler: %s", type(e).__name__)
        text = ""
    if not text or not text.strip():
        text = "⚠️ Die KI-Antwort ist gerade nicht verfügbar. Deine Frage wurde empfangen. Bitte versuche es später erneut; /status und /training funktionieren ohne KI."
    await _answer_markdown(message, text)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not _authorized(message):
        return
    await progress(message, "⏳ Hole Schnellstatus…")
    try:
        snapshot = await insights.get_daily_snapshot()
        latest_weight = await db.get_latest_renpho(settings.data_dir)
        weight_str = f"{latest_weight['weight_kg']} kg" if latest_weight else "–"
        readiness = snapshot.get("readiness") or {}
        rehab_label = formatter._readiness_label(readiness.get('score'), snapshot.get('knee_rehab_active', True))
        text = (
            f"⚡ *Schnellstatus*\n\n"
            f"🎯 Readiness: {formatter.fmt_score(readiness.get('score'))} — {rehab_label}\n"
            f"🔋 Body Battery: {snapshot.get('body_battery') if snapshot.get('body_battery') is not None else '–'}\n"
            f"❤️ HRV: {snapshot.get('avg_hrv') if snapshot.get('avg_hrv') is not None else '–'} ms\n"
            f"💓 Ruhe-Puls: {snapshot.get('resting_hr') if snapshot.get('resting_hr') is not None else '–'} bpm\n"
            f"👣 Schritte: {formatter.fmt_steps(snapshot.get('steps', 0), snapshot.get('steps_source', ''))}\n"
            f"💤 Schlaf: {formatter.fmt_duration(snapshot.get('sleep_duration_minutes'))}\n"
            f"⚖️ Gewicht: {weight_str}"
        )
    except Exception as e:
        logger.error("/status Fehler: %s", type(e).__name__)
        text = "⚠️ Fehler beim Laden des Status."
    await _answer_markdown(message, text)


@router.message()
async def cmd_unknown(message: Message) -> None:
    if not _authorized(message):
        return
    text = ("Diesen Befehl kenne ich noch nicht. /hilfe zeigt die verfügbaren Befehle."
            if message.text else
            "Bitte schick mir deine Frage als Text. Sprachaufnahmen, Fotos und Dateien kann ich hier noch nicht auswerten.")
    await _answer_markdown(message, text)
