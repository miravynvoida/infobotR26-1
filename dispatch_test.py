"""Симуляция реальных апдейтов через диспетчер (как в проде).

Сеть отключена специально: если путь доходит до TelegramNetworkError —
значит, вся логика отработала и бот пытался отправить ответ (это успех).
NameError/TypeError/AttributeError — настоящий баг в коде.
"""
import asyncio
import os
import tempfile
from datetime import datetime, timezone

tmp = tempfile.mkdtemp(prefix="r261dp_")
os.environ["DATA_DIR"] = tmp
os.environ["DB_PATH"] = os.path.join(tmp, "bot.db")
os.environ["BOT_TOKEN"] = "123456:TEST"
os.environ["ADMIN_IDS"] = "555"

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Message, Update, User as TgUser  # noqa: E402

from bot import db  # noqa: E402
from bot.handlers import build_dispatcher  # noqa: E402

uid = 555
_msg_id = 0


def make_message(text: str) -> Message:
    global _msg_id
    _msg_id += 1
    return Message(
        message_id=_msg_id,
        date=datetime.now(timezone.utc),
        chat=Chat(id=uid, type="private"),
        from_user=TgUser(id=uid, is_bot=False, first_name="Тест"),
        text=text,
    )


def make_update(text: str) -> Update:
    return Update(update_id=datetime.now().microsecond, message=make_message(text))


def make_cb_update(data: str) -> Update:
    global _msg_id
    _msg_id += 1
    return Update(
        update_id=datetime.now().microsecond,
        callback_query=CallbackQuery(
            id=str(_msg_id),
            from_user=TgUser(id=uid, is_bot=False, first_name="Тест"),
            chat_instance=str(uid),
            data=data,
            message=make_message("menu"),
        ),
    )


async def run(dp: Dispatcher, bot: Bot, label: str, update: Update) -> bool:
    try:
        await dp.feed_update(bot, update)
        print(f"  OK  {label} (обработан без исключений)")
        return True
    except Exception as e:
        name = type(e).__name__
        if name in ("TelegramNetworkError", "TelegramTokenValidationError", "TokenValidationError"):
            print(f"  OK  {label} — дошёл до отправки в Telegram (сеть выключена в тесте)")
            return True
        print(f"FAIL  {label} -> {name}: {e}")
        return False


async def main() -> int:
    db.init()
    st = db.all_students()[0]
    db.link_tg(st["id"], uid)

    bot = Bot("123456:TEST", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()

    results = []
    for label, upd in [
        ("/start (авторизованный)", make_update("/start")),
        ("/id", make_update("/id")),
        ("обычный текст", make_update("привет")),
        ("/help", make_update("/help")),
        ("/cancel", make_update("/cancel")),
        ("/start повторно", make_update("/start")),
        ("callback home", make_cb_update("home")),
        ("callback sch", make_cb_update("sch")),
        ("callback hw", make_cb_update("hw")),
        ("callback cab", make_cb_update("cab")),
    ]:
        results.append(await run(dp, bot, label, upd))
    print(f"\nИтого: OK={sum(results)}, FAIL={len(results) - sum(results)}")
    return 0 if all(results) else 1


sys = __import__("sys")
sys.exit(asyncio.run(main()))
