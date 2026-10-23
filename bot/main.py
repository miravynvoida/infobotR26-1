"""Точка входа: polling бота + uvicorn (API мини-приложения) в отдельном потоке + планировщик."""
import asyncio
import logging
import threading

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from . import config, db
from .handlers import build_dispatcher
from .services.jobs import make_scheduler

log = logging.getLogger("bot")


def start_api_thread() -> "object":
    import uvicorn

    from .api import app

    server = uvicorn.Server(
        uvicorn.Config(app, host="0.0.0.0", port=config.cfg.port, log_level="warning", access_log=False)
    )
    t = threading.Thread(target=server.run, name="api", daemon=True)
    t.start()
    return server


async def main() -> None:
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:  # защита от кракозябр/падения print с кириллицей в логах контейнера
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if not config.cfg.bot_token:
        raise SystemExit(
            "BOT_TOKEN не задан! Добавьте его в переменные окружения (панель хостинга) "
            "или в файл data/.env — см. .env.example."
        )
    db.init()

    bot = Bot(config.cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    server = start_api_thread()
    scheduler = make_scheduler(bot)
    scheduler.start()
    log.info(
        "Бот запущен: %s | студентов: %d | дисциплин: %d | порт: %d | группа: %s",
        config.BUILD_TAG, len(db.all_students()), len(db.all_disciplines()),
        config.cfg.port, config.cfg.group_name,
    )

    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        server.should_exit = True
        await bot.session.close()
        log.info("Бот остановлен.")


def run() -> None:
    asyncio.run(main())
