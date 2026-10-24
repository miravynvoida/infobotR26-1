"""Общие клавиатуры бота."""
import calendar as _cal
from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from . import config, db
from .services import schedule_utils as su

BTN = InlineKeyboardButton
KB = InlineKeyboardMarkup


def _grid(items: list[tuple[str, str]], cols: int = 2) -> list[list[BTN]]:
    return [
        [BTN(text=t, callback_data=cd) for t, cd in items[i : i + cols]]
        for i in range(0, len(items), cols)
    ]


# ---------------------------------------------------------------- главное меню

def main_menu(is_admin: bool) -> KB:
    rows = [
        [BTN(text="📅 Расписание", callback_data="sch"), BTN(text="📚 ДЗ", callback_data="hw")],
        [BTN(text="📖 Учебники", callback_data="tb"), BTN(text="👤 Кабинет", callback_data="cab")],
    ]
    if config.cfg.webapp_url:
        rows.append(
            [BTN(text="🖥 Открыть приложение", web_app=WebAppInfo(url=config.cfg.webapp_url))]
        )
    if is_admin:
        rows.append([BTN(text="🛠 Админ-панель", callback_data="adm")])
    rows.append([BTN(text="❓ Помощь", url=config.cfg.support_url)])
    return KB(inline_keyboard=rows)


# ---------------------------------------------------------------- расписание

def sch_menu_kb() -> KB:
    return KB(
        inline_keyboard=[
            [BTN(text="📅 Сегодня", callback_data=f"sch:d:{su.iso(su.today())}"),
             BTN(text="📅 Завтра", callback_data=f"sch:d:{su.iso(su.today() + timedelta(days=1))}")],
            [BTN(text="🗓 Выбрать день", callback_data="sch:cal")],
            [BTN(text="🏠 Главное меню", callback_data="home")],
        ]
    )


def day_nav_kb(day_iso: str) -> KB:
    d = date.fromisoformat(day_iso)
    prev = su.iso(d - timedelta(days=1))
    nxt = su.iso(d + timedelta(days=1))
    return KB(
        inline_keyboard=[
            [BTN(text="◀ Пред. день", callback_data=f"sch:d:{prev}"),
             BTN(text="След. день ▶", callback_data=f"sch:d:{nxt}")],
            [BTN(text="🗓 Выбрать день", callback_data="sch:cal")],
            [BTN(text="🏠 Главное меню", callback_data="home")],
        ]
    )


def month_kb(year: int, month: int, prefix: str, today_iso: str, footer: tuple[str, str]) -> KB:
    py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    rows = [
        [
            BTN(text="◀", callback_data=f"{prefix}cal:{py:04d}-{pm:02d}"),
            BTN(text=f"{su.MONTHS[month - 1]} {year}", callback_data="noop"),
            BTN(text="▶", callback_data=f"{prefix}cal:{ny:04d}-{nm:02d}"),
        ],
        [BTN(text=w, callback_data="noop") for w in ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")],
    ]
    for week in _cal.monthcalendar(year, month):
        row = []
        for d in week:
            if d == 0:
                row.append(BTN(text=" ", callback_data="noop"))
                continue
            diso = f"{year:04d}-{month:02d}-{d:02d}"
            row.append(BTN(text=f"{d}*" if diso == today_iso else str(d), callback_data=f"{prefix}d:{diso}"))
        rows.append(row)
    rows.append([BTN(text=footer[0], callback_data=footer[1])])
    return KB(inline_keyboard=rows)


# ---------------------------------------------------------------- дз (студент)

def hw_menu_kb() -> KB:
    hw = db.active_homework()
    if not hw:
        return KB(
            inline_keyboard=[
                [BTN(text="📭 Домашних заданий нет", callback_data="noop")],
                [BTN(text="📥 Выполненные", callback_data="hw:dl")],
                [BTN(text="🏠 Главное меню", callback_data="home")],
            ]
        )
    items = []
    seen: set[int] = set()
    for h in hw:
        if h["discipline_id"] in seen:
            continue
        seen.add(h["discipline_id"])
        items.append((f"{h['emoji']} {h['discipline']}", f"hw:{h['discipline_id']}"))
    rows = _grid(items, 2)
    rows.append([BTN(text="📥 Выполненные", callback_data="hw:dl")])
    rows.append([BTN(text="🏠 Главное меню", callback_data="home")])
    return KB(inline_keyboard=rows)


def hw_menu_new_kb(unviewed: set[int]) -> KB:
    hw = db.active_homework()
    items = []
    seen: set[int] = set()
    for h in hw:
        if h["discipline_id"] in seen:
            continue
        seen.add(h["discipline_id"])
        new = any(x["id"] in unviewed for x in hw if x["discipline_id"] == h["discipline_id"])
        mark = "✳️ " if new else ""
        items.append((f"{mark}{h['emoji']} {h['discipline']}", f"hw:{h['discipline_id']}"))
    if not items:
        return hw_menu_kb()
    rows = _grid(items, 2)
    rows.append([BTN(text="📥 Выполненные", callback_data="hw:dl")])
    rows.append([BTN(text="🏠 Главное меню", callback_data="home")])
    return KB(inline_keyboard=rows)


def hw_list_kb(disc_id: int, done_ids: set[int]) -> KB:
    hw = [h for h in db.active_homework() if h["discipline_id"] == disc_id]
    rows = []
    for h in hw:
        due = su.fmt_dm(h["due_date"]) if h.get("due_date") else "—"
        clip = "📎" if h.get("files") and h["files"] not in ("[]", "") else ""
        check = "✅ " if h["id"] in done_ids else ""
        rows.append([BTN(text=f"{check}{due} • {h['title']} {clip}", callback_data=f"hw:v:{h['id']}")])
    rows.append([BTN(text="◀ Назад к дисциплинам", callback_data="hw")])
    rows.append([BTN(text="🏠 Главное меню", callback_data="home")])
    return KB(inline_keyboard=rows)


def hw_detail_kb(hid: int, disc_id: int, done: bool) -> KB:
    return KB(
        inline_keyboard=[
            [
                BTN(
                    text="↩️ Не выполнено" if done else "✅ Выполнено",
                    callback_data=f"hw:done:{hid}",
                ),
                BTN(text="◀ К дисциплине", callback_data=f"hw:{disc_id}"),
            ],
            [BTN(text="🏠 Главное меню", callback_data="home")],
        ]
    )


def hw_done_list_kb(student_id: int) -> KB:
    rows = db.q(
        "SELECT h.id, h.title, h.due_date, h.archived, d.name AS discipline, d.emoji FROM homework_done hd "
        "JOIN homework h ON h.id = hd.homework_id JOIN disciplines d ON d.id = h.discipline_id "
        "WHERE hd.student_id = ? ORDER BY h.archived, h.due_date",
        (student_id,),
    )
    if not rows:
        return KB(
            inline_keyboard=[
                [BTN(text="📭 Пока ничего не отмечено", callback_data="noop")],
                [BTN(text="◀ К дисциплинам", callback_data="hw")],
            ]
        )
    kb_rows = [
        [BTN(text=f"✅ {su.fmt_dm(r['due_date'])} • {r['title']}", callback_data=f"hw:v:{r['id']}")]
        for r in rows
    ]
    kb_rows.append([BTN(text="◀ К дисциплинам", callback_data="hw")])
    return KB(inline_keyboard=kb_rows)


# ---------------------------------------------------------------- учебники

def tb_menu_kb() -> KB:
    tbs = db.all_textbooks()
    if not tbs:
        return KB(
            inline_keyboard=[
                [BTN(text="📭 Учебников пока нет", callback_data="noop")],
                [BTN(text="🏠 Главное меню", callback_data="home")],
            ]
        )
    items = []
    seen: set[int] = set()
    for t in tbs:
        if t["discipline_id"] in seen:
            continue
        seen.add(t["discipline_id"])
        items.append((f"{t['emoji']} {t['discipline']}", f"tb:{t['discipline_id']}"))
    rows = _grid(items, 2)
    rows.append([BTN(text="🏠 Главное меню", callback_data="home")])
    return KB(inline_keyboard=rows)


def tb_list_kb(disc_id: int) -> KB:
    rows = [
        [BTN(text=t["title"], callback_data=f"tb:v:{t['id']}")]
        for t in db.textbooks_by_discipline(disc_id)
    ]
    rows.append([BTN(text="◀ Назад к дисциплинам", callback_data="tb")])
    rows.append([BTN(text="🏠 Главное меню", callback_data="home")])
    return KB(inline_keyboard=rows)


def tb_detail_kb(tid: int, disc_id: int) -> KB:
    return KB(
        inline_keyboard=[
            [BTN(text="◀ К дисциплине", callback_data=f"tb:{disc_id}")],
            [BTN(text="🏠 Главное меню", callback_data="home")],
        ]
    )


# ---------------------------------------------------------------- кабинет

def cab_kb(s: dict) -> KB:
    return KB(
        inline_keyboard=[
            [
                BTN(
                    text=f"🔔 Пары: {'ВКЛ' if s['next_pair'] else 'выкл'}",
                    callback_data="cab:np:tgl",
                ),
                BTN(text=f"⏱ за {s['next_pair_min']} мин", callback_data="cab:np:menu"),
            ],
            [
                BTN(
                    text=f"📅 Завтра: {'ВКЛ' if s['tomorrow'] else 'выкл'}",
                    callback_data="cab:tm:tgl",
                ),
                BTN(text=f"🕐 {s['tomorrow_time']}", callback_data="cab:tm:menu"),
            ],
            [
                BTN(
                    text=f"📚 ДЗ на завтра: {'ВКЛ' if s.get('hw_tomorrow') else 'выкл'}",
                    callback_data="cab:hw:tgl",
                ),
                BTN(text=f"🕐 {s.get('hw_tomorrow_time') or '18:00'}", callback_data="cab:hw:menu"),
            ],
            [
                BTN(
                    text=f"💤 Прочие: {'ВКЛ' if s['misc'] else 'выкл'}",
                    callback_data="cab:ms:tgl",
                )
            ],
            [
                BTN(
                    text=f"😴 Тихая пара: {'ВКЛ' if s.get('quiet') else 'выкл'}",
                    callback_data="cab:q:tgl",
                )
            ],
            [BTN(text="🏠 Главное меню", callback_data="home")],
        ]
    )


def minutes_kb() -> KB:
    vals = [5, 10, 15, 30, 45, 60, 90]
    rows = _grid([(f"{v} мин", f"cab:np:{v}") for v in vals], 4)
    rows.append([BTN(text="◀ Назад", callback_data="cab")])
    return KB(inline_keyboard=rows)


def hw_times_kb() -> KB:
    vals = ["16:00", "17:00", "18:00", "19:00", "20:00", "21:00"]
    rows = _grid([(v, f"cab:hw:{v}") for v in vals], 3)
    rows.append([BTN(text="◀ Назад", callback_data="cab")])
    return KB(inline_keyboard=rows)


def times_kb() -> KB:
    vals = ["17:00", "18:00", "19:00", "20:00", "21:00", "22:00"]
    rows = _grid([(v, f"cab:tm:{v}") for v in vals], 3)
    rows.append([BTN(text="✍️ Другое время", callback_data="cab:tm:c")])
    rows.append([BTN(text="◀ Назад", callback_data="cab")])
    return KB(inline_keyboard=rows)


# ---------------------------------------------------------------- посещаемость

def attendance_kb(day_iso: str) -> KB:
    d = day_iso.replace("-", "")
    return KB(
        inline_keyboard=[
            [BTN(text="✅ Да, буду на всех", callback_data=f"att:full:{d}"),
             BTN(text="❌ Не буду", callback_data=f"att:none:{d}")],
            [BTN(text="⚖️ Частично", callback_data=f"att:partial:{d}"),
             BTN(text="🤒 Заболел", callback_data=f"att:sick:{d}")],
            [BTN(text="🗑 Сбросить мой ответ", callback_data=f"att:reset:{d}")],
        ]
    )


def attendance_pair_kb(day_iso: str, pair_no: int) -> KB:
    d = day_iso.replace("-", "")
    return KB(
        inline_keyboard=[
            [BTN(text="✅ Буду", callback_data=f"att2:y:{pair_no}:{d}"),
             BTN(text="❌ Не буду", callback_data=f"att2:n:{pair_no}:{d}")],
        ]
    )


def attendance_pick_kb(day_iso: str, lessons: list[dict], missing: set[int]) -> KB:
    rows = []
    for ls in lessons:
        mark = "❌" if ls["pair_no"] in missing else "▫️"
        rows.append(
            [
                BTN(
                    text=f"{mark} {ls['pair_no']} • {ls['start']} {ls['discipline']}",
                    callback_data=f"att:t:{ls['pair_no']}",
                )
            ]
        )
    rows.append([BTN(text="✅ Подтвердить", callback_data="att:ok")])
    return KB(inline_keyboard=rows)


# ---------------------------------------------------------------- онбординг

def onb_yes_no(prefix: str) -> KB:
    return KB(
        inline_keyboard=[
            [BTN(text="✅ Да", callback_data=f"{prefix}:1"), BTN(text="❌ Нет", callback_data=f"{prefix}:0")],
        ]
    )


def onb_minutes_kb() -> KB:
    rows = _grid([(f"{v} мин", f"onb:pm:{v}") for v in (5, 10, 15, 30, 45, 60, 90)], 4)
    return KB(inline_keyboard=rows)


def onb_times_kb() -> KB:
    rows = _grid([(v, f"onb:tt:{v}") for v in ("17:00", "18:00", "19:00", "20:00", "21:00", "22:00")], 3)
    rows.append([BTN(text="✍️ Другое время", callback_data="onb:tt:c")])
    return KB(inline_keyboard=rows)


def onb_theme_kb() -> KB:
    return KB(
        inline_keyboard=[
            [BTN(text="🌑 Тёмная", callback_data="onb:th:dark"), BTN(text="☀️ Светлая", callback_data="onb:th:light")],
        ]
    )
