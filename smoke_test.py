"""Smoke-тест: инициализация БД, импорт расписания, недели, ДЗ, посещаемость, диспетчер, API."""
import json
import os
import sys
import tempfile
from datetime import date, datetime

tmp = tempfile.mkdtemp(prefix="r261_")
os.environ["DATA_DIR"] = tmp
os.environ["DB_PATH"] = os.path.join(tmp, "bot.db")
os.environ["BOT_TOKEN"] = "123456:TESTTOKEN"
os.environ["ADMIN_IDS"] = "11111111"

from bot import config, db  # noqa: E402
from bot.services import schedule_utils as su  # noqa: E402

ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK  {name}")
    else:
        fail += 1
        print(f"FAIL  {name} {extra}")


print("== init ==")
db.init()
students = db.all_students()
disciplines = db.all_disciplines()
check("25 студентов", len(students) == 25, len(students))
check("15 дисциплин", len(disciplines) == 15, len(disciplines))
check("коды уникальны 6 симв.", len({s["code"] for s in students}) == 25 and all(len(s["code"]) == 6 for s in students))
check("группа Р 26-1 (русская Р)", config.cfg.group_name == "Р 26-1")

print("== недели ==")
check("2–6.09.2026 = неделя 1", su.study_week(date(2026, 9, 2)) == 1 and su.study_week(date(2026, 9, 6)) == 1)
check("7.09.2026 = неделя 2", su.study_week(date(2026, 9, 7)) == 2)
check("19–25.10.2026 = неделя 8", su.study_week(date(2026, 10, 19)) == 8 and su.study_week(date(2026, 10, 25)) == 8)
check("26.10.2026 = неделя 9", su.study_week(date(2026, 10, 26)) == 9)
s8, e8 = su.week_bounds(8)
check("границы 8-й недели 19–25.10", s8 == date(2026, 10, 19) and e8 == date(2026, 10, 25))

print("== импорт JSON (пример пользователя) ==")
TOMORROW = su.iso(su.today() + __import__("datetime").timedelta(days=1))
sample = {
    "format_version": 1,
    "group": "Р 26-1",
    "weeks": [
        {
            "week_number": 8,
            "start_date": "2026-10-19",
            "end_date": "2026-10-25",
            "lessons": [
                {"date": "2026-10-23", "start": "08:30", "end": "10:00", "discipline": "Обществознание", "lesson_type": "ЛЕК", "room": "415"},
                {"date": "2026-10-23", "start": "10:10", "end": "11:40", "discipline": "Физ. культура", "lesson_type": "ПР", "room": "С/зал"},
                {"date": "2026-10-23", "start": "11:50", "end": "13:20", "discipline": "Математика", "lesson_type": "ПР", "room": "417"},
                {"date": "2026-10-24", "start": "08:30", "end": "10:00", "discipline": "Информатика", "lesson_type": "ПР", "room": "417"},
                {"date": TOMORROW, "start": "08:30", "end": "10:00", "discipline": "Математика", "lesson_type": "ЛЕК", "room": "415"},
            ],
        }
    ],
    "warnings": [],
}
report = su.import_schedule_json(json.dumps(sample, ensure_ascii=False))
check("импорт: 1 неделя", report["weeks"] == 1)
check("импорт: 3 дня", report["days"] == 3, report["days"])
check("импорт: 5 занятий", report["lessons"] == 5, report["lessons"])
lessons = db.day_lessons("2026-10-23")
check("3 пары 23.10", len(lessons) == 3, lessons)
check("пара 2 = Физ. культура", lessons[1]["discipline"] == "Физ. культура" and lessons[1]["pair_no"] == 2)
check("аудитория С/зал", lessons[1]["room"] == "С/зал")

print("== формат расписания (как в примере) ==")
text = su.day_view_html("2026-10-23", su.now(), with_statuses=True)
check("шапка с датой", "Пятница, 23.10.2026" in text)
check("легенда статусов", "прошла • 🔴 идёт сейчас • ⏳" in text)
check("строка пары", "08:30–10:00 — 1 пара | ЛЕК" in text)
check("преподаватель и ауд.", "Алексеева Л.М. • ауд. 415" in text)
check("эмодзи дисциплин", "⚖️ <b>Обществознание</b>" in text and "📐 <b>Математика</b>" in text)
plain = su.day_view_html("2026-10-24", su.now(), with_statuses=False)
check("завтра без легенды", "Обозначения" not in plain)

print("== статус главного меню ==")
n = datetime(2026, 10, 23, 10, 15, tzinfo=su.TZ)
st = su.main_status_html(n)
check("10:15 — идёт 2 пара", "Сейчас идёт 2 пара • Физ. культура (ПР)" in st, st)
n2 = datetime(2026, 10, 23, 7, 5, tzinfo=su.TZ)
st2 = su.main_status_html(n2)
check("07:05 — до первой пары", "1 пара • Обществознание" in st2, st2)
n3 = datetime(2026, 10, 23, 14, 0, tzinfo=su.TZ)
check("14:00 — пар больше нет", "пар больше нет" in su.main_status_html(n3))

print("== ДЗ ==")
did = db.discipline_by_name("Математика")["id"]
hid = db.create_hw(did, "Логарифмы", "№ 45–50 из учебника", su.iso(su.today()), "ПР", None, [], su.ts(), 1)
hw = db.hw_by_id(hid)
check("создано ДЗ", hw["title"] == "Логарифмы")
check("опции сдачи от расписания", [o["date"] for o in su.next_lesson_options(did)][0] == TOMORROW)
db.archive_due_homework(su.iso(su.today()), su.ts())
check("архивация в день сдачи", db.hw_by_id(hid)["archived"] == 1)

print("== оценки (парсер) ==")
from bot.services.grades import parse_mark, parse_header_date  # noqa: E402
check("parse_mark 5", parse_mark("5") == ["5"])
check("parse_mark Н/Б/О", parse_mark("Н") == ["Н"] and parse_mark("б") == ["Б"] and parse_mark("o") == ["О"])
check("parse_mark зачет", parse_mark("Зачет") == ["Зачет"] and parse_mark("незачет") == ["Незачет"])
check("parse_mark 5,4", parse_mark("5,4") == ["5", "4"])
check("parse_mark через дробь 5/5", parse_mark("5/5") == ["5", "5"])
check("parse_mark через дробь 5/4/3", parse_mark("5/4/3") == ["5", "4", "3"])
check("дата шапки", parse_header_date("23.10.2026") == "2026-10-23")

print("== посещаемость ==")
st1 = students[0]
st2 = students[1]
db.link_tg(st1["id"], 1000001)
db.link_tg(st2["id"], 1000002)
db.set_attendance("2026-10-23", st1["id"], "full", [], su.ts())
db.set_attendance("2026-10-23", st2["id"], "partial", [2, 3], su.ts())
summ = __import__("bot.services.attendance", fromlist=["summary"]).summary("2026-10-23")
check("1 на всех парах", summ["full_count"] == 1)
check("частично с парами 2,3", summ["partial"] and summ["partial"][0][1] == "2, 3")

print("== disptcher + api ==")
from bot.handlers import build_dispatcher  # noqa: E402

dp = build_dispatcher()
check("диспетчер собран", dp is not None)
from bot.api import app  # noqa: E402

routes = [r.path for r in app.routes]
for need in ["/api/auth", "/api/me", "/api/today", "/api/schedule/week/{n}", "/api/homework",
             "/api/grades", "/api/attendance", "/api/admin/stats", "/api/admin/homework",
             "/api/admin/schedule/import", "/api/admin/upload", "/api/admin/broadcast"]:
    check("route " + need, need in routes)

print("== middleware авторизации ==")
import asyncio  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import bot.middlewares as mw_mod  # noqa: E402
from bot.middlewares import AuthMiddleware  # noqa: E402


class FakeMsg:
    def __init__(self, text=""):
        self.text = text
        self.answered = []

    async def answer(self, text, **kw):
        self.answered.append(text)


class FakeCb(FakeMsg):
    pass


# подменяем классы, чтобы isinstance-проверки работали на фейках
mw_mod.CallbackQuery = FakeCb


async def mw_checks():
    mw = AuthMiddleware()
    called = []

    async def handler(event, data):
        called.append(data)

    anon = {"event_from_user": SimpleNamespace(id=999999999, is_bot=False)}
    await mw(handler, FakeMsg("/start"), dict(anon))
    check("anon /start пропущен к хендлеру", len(called) == 1)
    m = FakeMsg("Аносов Владимир Сергеевич")
    await mw(handler, m, dict(anon))
    check("anon текст (ФИО) пропущен — вход не рушим", len(called) == 2 and not m.answered)
    cb = FakeCb()
    await mw(handler, cb, dict(anon))
    check("anon callback заблокирован", len(called) == 2 and "Нет доступа" in cb.answered[0])
    check("anon: student=None в data", called[0].get("student") is None)

    st9 = db.all_students()[0]
    db.link_tg(st9["id"], 888888888)
    auth = {"event_from_user": SimpleNamespace(id=888888888, is_bot=False)}
    await mw(handler, FakeMsg("текст"), dict(auth))
    check("авторизованный пропущен, student есть", len(called) == 3 and called[2]["student"]["id"] == st9["id"])
    admin = {"event_from_user": SimpleNamespace(id=11111111, is_bot=False)}
    await mw(handler, FakeMsg(), dict(admin))
    check("data.is_admin из ADMIN_IDS", called[3]["is_admin"] is True)


asyncio.run(mw_checks())

print("== клавиатуры ==")
from bot.keyboards import month_kb, main_menu, hw_menu_kb  # noqa: E402

kb = month_kb(2026, 10, "sch:", "2026-10-23", ("🏠 Главное меню", "home"))
flat = [b for row in kb.inline_keyboard for b in row]
check("календарь: сегодня со звёздочкой", any(b.text == "23*" for b in flat))
check("календарь: заголовок Октябрь 2026", any(b.text == "Октябрь 2026" for b in flat))
mm = main_menu(True)
flat = [b for row in mm.inline_keyboard for b in row]
check("меню: 4 строки админа без webapp", len(mm.inline_keyboard) == 4, len(mm.inline_keyboard))
config.cfg.webapp_url  # noqa
import bot.keyboards as kbmod  # noqa: E402

orig = config.cfg.webapp_url
object.__setattr__(config.cfg, "webapp_url", "https://app.example.com")
mm2 = main_menu(True)
flat2 = [b for row in mm2.inline_keyboard for b in row]
check("меню: 5 строк с webapp-кнопкой", len(mm2.inline_keyboard) == 5, len(mm2.inline_keyboard))
check("меню: webapp-кнопка", any(getattr(b, "web_app", None) for b in flat2))
check("меню: студент без админки — 4 строки", len(main_menu(False).inline_keyboard) == 4)
check("меню: кнопка помощи-ссылка", any(b.url for b in flat))

print(f"\nИтого: OK={ok}, FAIL={fail}")
sys.exit(1 if fail else 0)
