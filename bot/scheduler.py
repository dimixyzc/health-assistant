"""
Proaktive tägliche/wöchentliche Nachrichten via APScheduler.
"""
import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from analytics import insights, formatter
from ai.openai_client import OpenAIHealthAssistant
from connectors import garmin as garmin_conn
from storage import database as db
from config import settings

logger = logging.getLogger(__name__)


async def send_morning_briefing(bot: Bot, ai: OpenAIHealthAssistant) -> None:
    try:
        snapshot = await insights.get_daily_snapshot()
        text = await ai.generate_morning_briefing(snapshot)
        text += "\n\n" + formatter.morning_briefing(snapshot)
        await bot.send_message(settings.telegram_chat_id, text, parse_mode="Markdown")
        logger.info("Morgen-Briefing gesendet")
    except Exception as e:
        logger.error(f"Morgen-Briefing Fehler: {e}")
        await bot.send_message(settings.telegram_chat_id, "⚠️ Morgen-Briefing konnte nicht geladen werden.")


async def send_evening_summary(bot: Bot, ai: OpenAIHealthAssistant) -> None:
    try:
        snapshot = await insights.get_daily_snapshot()
        activities = await garmin_conn.get_recent_activities(
            settings.garmin_email, settings.garmin_password, settings.data_dir, limit=5
        )
        today_activities = [
            a for a in activities
            if a.get("start_time", "").startswith(snapshot["date"])
        ]
        text = await ai.generate_evening_summary(snapshot, today_activities)
        text += "\n\n" + formatter.evening_summary(snapshot, today_activities)
        await bot.send_message(settings.telegram_chat_id, text, parse_mode="Markdown")
        logger.info("Abend-Zusammenfassung gesendet")
    except Exception as e:
        logger.error(f"Abend-Zusammenfassung Fehler: {e}")


async def send_weekly_review(bot: Bot, ai: OpenAIHealthAssistant) -> None:
    try:
        weekly = await insights.get_weekly_summary()
        text = await ai.generate_weekly_summary(weekly)
        text += "\n\n" + formatter.weekly_summary(weekly)
        await bot.send_message(settings.telegram_chat_id, text, parse_mode="Markdown")
        logger.info("Wochen-Review gesendet")
    except Exception as e:
        logger.error(f"Wochen-Review Fehler: {e}")


async def check_renpho_reminder(bot: Bot) -> None:
    try:
        days = await db.days_since_last_renpho(settings.data_dir)
        if days is None or days >= settings.renpho_reminder_days:
            actual_days = days or 999
            text = formatter.renpho_reminder(actual_days)
            await bot.send_message(settings.telegram_chat_id, text, parse_mode="Markdown")
            logger.info(f"Renpho-Erinnerung gesendet (letzte Messung vor {actual_days} Tagen)")
    except Exception as e:
        logger.error(f"Renpho-Reminder Fehler: {e}")


def setup_scheduler(bot: Bot, ai: OpenAIHealthAssistant) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Berlin")

    # Morgen-Briefing 07:30
    scheduler.add_job(
        send_morning_briefing,
        CronTrigger(hour=7, minute=30, timezone="Europe/Berlin"),
        args=[bot, ai],
        id="morning_briefing",
        name="Morgen-Briefing",
        replace_existing=True,
    )

    # Abend-Zusammenfassung 20:00
    scheduler.add_job(
        send_evening_summary,
        CronTrigger(hour=20, minute=0, timezone="Europe/Berlin"),
        args=[bot, ai],
        id="evening_summary",
        name="Abend-Zusammenfassung",
        replace_existing=True,
    )

    # Wöchentlicher Review — Sonntag 18:00
    scheduler.add_job(
        send_weekly_review,
        CronTrigger(day_of_week="sun", hour=18, minute=0, timezone="Europe/Berlin"),
        args=[bot, ai],
        id="weekly_review",
        name="Wochen-Review",
        replace_existing=True,
    )

    # Renpho-Erinnerung täglich 07:30 (nur wenn überfällig)
    scheduler.add_job(
        check_renpho_reminder,
        CronTrigger(hour=7, minute=30, timezone="Europe/Berlin"),
        args=[bot],
        id="renpho_reminder",
        name="Renpho-Erinnerung",
        replace_existing=True,
    )

    return scheduler
