"""Тест всех inline-кнопок: каждая должна найти свой хендлер, а не fallback."""
import asyncio
import os
import tempfile
from datetime import datetime, timezone

tmp = tempfile.mkdtemp(prefix="r261cb_")
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
from bot.services import schedule_utils as su  # noqa: E402

uid = 555
_mid = 0


def msg() -> Message:
    global _mid
    _mid += 1
    return Message(
        message_id=_mid, date=datetime.now(timezone.utc),
        chat=Chat(id=uid, type="private"),
        from_user=TgUser(id=uid, is_bot=False, first_name="Т"),
        text="x",
    )


def upd(data: str) -> Update:
    global _mid
    _mid += 1
    return Update(
        update_id=_mid,
        callback_query=CallbackQuery(
            id=str(_mid), from_user=TgUser(id=uid, is_bot=False, first_name="Т"),
            chat_instance=str(uid), data=data, message=msg(),
        ),
    )


class FallbackHit(Exception):
    pass


async def fake_fallback(cb, *a, **kw):
    raise FallbackHit(cb.data)


async def main() -> int:
    db.init()
    db.link_tg(db.all_students()[0]["id"], uid)
    did = db.discipline_by_name("Математика")["id"]
    hid = db.create_hw(did, "Т", "Т", None, None, None, [], su.ts(), None)
    db.create_textbook(did, "Уч", None, [])

    # подменяем fallback, чтобы его срабатывание считалось провалом
    import bot.handlers.menu as menu_mod

    menu_mod.fallback_cb = fake_fallback

    dp = build_dispatcher()
    bot = Bot("123456:TEST", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # сеть выключаем мгновенной ошибкой (иначе каждый вызов ждёт таймаут)
    class OfflineAPI(Exception):
        pass

    from unittest.mock import AsyncMock

    offline_exc = OfflineAPI("offline")
    sess = AsyncMock(side_effect=offline_exc)
    sess.make_request = AsyncMock(side_effect=offline_exc)
    sess.stream_content = AsyncMock(side_effect=offline_exc)
    bot.session = sess

    cases = [
        "hw", f"hw:{did}", f"hw:v:{hid}", f"hw:done:{hid}", "hw:dl",
        "tb", f"tb:{did}", "tb:v:1",
        "sch", "sch:d:2026-10-24", "sch:cal", "sch:cal:2026-10",
        "cab", "cab:np:tgl", "cab:np:menu", "cab:np:30", "cab:tm:tgl", "cab:tm:menu", "cab:q:tgl",
        "cab:tm:19:00", "cab:tm:c", "cab:ms:tgl",
        "att:full:20261024", "att:none:20261024", "att:partial:20261024", "att:t:1", "att:ok",
        "home", "noop", "cab:hw:tgl", "cab:hw:menu", "cab:hw:18:00", "adm:mnt", "adm:exam", "adm:backup", "adm:restore", "att:reset:20261024", "att2:y:1:20261024", "att2:n:2:20261024", "adm:ask", "adm:ask:day", "adm:ask:p:1",
        # админ-панель
        "adm", "adm:hw", "adm:hw:new", "adm:hw:l", "adm:hw:arc", f"adm:hw:d:{did}",
        f"adm:hw:i:{hid}", f"adm:hw:e:{hid}", f"adm:hw:f:{hid}:title", f"adm:hw:f:{hid}:due",
        f"adm:hw:f:{hid}:disc", f"adm:hw:f:{hid}:files", f"adm:hw:arc2:{hid}", f"adm:hw:res:{hid}",
        f"adm:hw:delc:{hid}", f"adm:hw:del:{hid}", f"hwd:disc:{did}", "hwd:due:0", "hwd:due:c",
        "hwd:nof", "hwd:fok", "hwd:pub", "hwd:rf", "hwd:rf:title", "hwd:rf:files",
        "hwd:fdel:0", "hwd:fadd", "hwd:fok2", "hwd:cancel", "hwd:rf:back", f"hwd:rdisc:{did}",
        f"ahwd:{hid}:0", f"ahwdc:{hid}", f"ahws:{hid}:{did}", f"ahwfd:{hid}:0",
        f"ahwfa:{hid}", f"ahwfw:{hid}",
        "adm:sch", "asch:imp", "asch:cal", "asch:cal:2026-10", "asch:d:2026-10-24",
        "asch:dn:2026-10-24:1", "asch:dx:2026-10-24", "asch:p:2026-10-24:1",
        "asch:pf:2026-10-24:1:disc", f"asch:pd:2026-10-24:1:{did}",
        "asch:pf:2026-10-24:1:type", "asch:pt:2026-10-24:1:ПР",
        "asch:pf:2026-10-24:1:room", "asch:pf:2026-10-24:1:time",
        "asch:pn:2026-10-24:1:2", "asch:pc:2026-10-24:1", "asch:px:2026-10-24:1",
        "asch:pa:2026-10-24", f"asch:pan:2026-10-24:2", f"asch:pad:2026-10-24:2:{did}",
        "asch:pat:2026-10-24:2:ПР",
        "adm:studs", "adm:stu:add", "adm:stu:1", "adm:stu:code:1", "adm:stu:unl:1",
        "adm:stu:mut:1", "adm:stu:unmut:1",
        "adm:stu:delc:1", "adm:stu:del:1",
        "adm:disc", "adm:di:add", "adm:di:1", "adm:di:f:1:name", "adm:di:f:1:emoji",
        "adm:di:f:1:teacher", "adm:di:delc:1", "adm:di:del:1",
        "adm:tb", f"adm:tbd:{did}", "adm:tb:new:1", "adm:tbi:1", "adm:tb:f:1:title",
        "adm:tb:f:1:desc", "adm:tb:fl:1", "atbd:0", "atbfa:1", "atbfw:1",
        "adm:tb:delc:1", "adm:tb:del:1", "atb:nof", "atb:done",
        "adm:st", "adm:sync", "adm:bc", "adm:bc:go",
    ]
    ok = fail = 0
    for data in cases:
        try:
            await dp.feed_update(bot, upd(data))
            ok += 1
            print(f"  OK  {data}", flush=True)
        except FallbackHit as e:
            fail += 1
            print(f"FAIL  {data} -> улетел в fallback (нет хендлера)", flush=True)
        except Exception as e:
            name = type(e).__name__
            if "Telegram" in name or "Token" in name or isinstance(e, OfflineAPI):
                ok += 1
                print(f"  OK  {data} (дошёл до Telegram API)", flush=True)
            else:
                fail += 1
                print(f"FAIL  {data} -> {name}: {e}", flush=True)
    print(f"\nИтого: OK={ok}, FAIL={fail}", flush=True)
    return 0 if fail == 0 else 1


import sys  # noqa: E402

sys.exit(asyncio.run(main()))
