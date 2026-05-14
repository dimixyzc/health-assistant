import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers.commands import router as commands_router
from bot.scheduler import setup_scheduler
from ai.openai_client import OpenAIHealthAssistant
from storage.database import init_db
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logging.getLogger("ai.openai_client").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    logger.info("Health Assistant startet...")
    await init_db(settings.data_dir)
    logger.info(f"DB initialisiert in {settings.data_dir}")
    await bot.send_message(
        settings.telegram_chat_id,
        "🤖 *Health Assistant gestartet!*\nTippe /hilfe für alle Befehle.",
        parse_mode="Markdown",
    )


async def main() -> None:
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()
    dp.include_router(commands_router)
    async def _startup():
        await on_startup(bot)

    dp.startup.register(_startup)

    ai = OpenAIHealthAssistant(settings.openai_api_key, settings.openai_model)
    scheduler = setup_scheduler(bot, ai)
    scheduler.start()
    logger.info("Scheduler gestartet")

    try:
        await dp.start_polling(bot, allowed_updates=["message"])
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
