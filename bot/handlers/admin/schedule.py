"""Управление расписанием (админ): импорт JSON + ручной редактор дней."""
import json
from datetime import date, timedelta
from io import BytesIO

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ... import db
from ...keyboards import month_kb
from ...services import schedule_utils as su
from ...states import SchEdSG, SchImpSG

router = Router()


def sch_admin_kb() -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="📥 Импорт JSON", callback_data="asch:imp")],
            [B(text="📅 Изменить по дням", callback_data="asch:cal")],
            [B(text="◀ Админ-панель", callback_data="adm")],
        ]
    )


def admin_day_view_html(day_iso: str) -> str:
    lessons = db.day_lessons(day_iso)
    head = f"{su.day_header_html(day_iso)}\n\n"
    if not lessons:
        return head + "📭 Расписание на этот день не опубликовано."
    return head + "\n\n".join(su.lesson_block_html(ls) for ls in lessons)


def admin_day_kb(day_iso: str) -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    lessons = db.day_lessons(day_iso)
    d = date.fromisoformat(day_iso)
    rows = []
    for ls in lessons:
        label = f"✏️ {ls['pair_no']} • {ls['discipline']} {ls['lesson_type'] or ''} {ls['start']}"
        rows.append([B(text=label, callback_data=f"asch:p:{day_iso}:{ls['pair_no']}")])
    rows.append([B(text="➕ Добавить пару" if lessons else "➕ Добавить расписание", callback_data=f"asch:pa:{day_iso}")])
    if lessons:
        rows.append([B(text="🗑 Удалить расписание", callback_data=f"asch:dx:{day_iso}")])
    rows.append(
        [B(text="◀ Пред. день", callback_data=f"asch:dn:{day_iso}:-1"),
         B(text="След. день ▶", callback_data=f"asch:dn:{day_iso}:1")]
    )
    rows.append([B(text="🗓 Календарь", callback_data="asch:cal"), B(text="◀ Админ-панель", callback_data="adm:sch")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_pair(day_iso: str, pair_no: int) -> dict | None:
    for ls in db.day_lessons(day_iso):
        if ls["pair_no"] == pair_no:
            return ls
    return None


def pair_menu_kb(day_iso: str, pair_no: int) -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="📐 Дисциплина", callback_data=f"asch:pf:{day_iso}:{pair_no}:disc"),
             B(text="🏷 Тип", callback_data=f"asch:pf:{day_iso}:{pair_no}:type")],
            [B(text="🚪 Аудитория", callback_data=f"asch:pf:{day_iso}:{pair_no}:room"),
             B(text="🕐 Время и номер", callback_data=f"asch:pf:{day_iso}:{pair_no}:time")],
            [B(text="🗑 Удалить пару", callback_data=f"asch:px:{day_iso}:{pair_no}")],
            [B(text="◀ К дню", callback_data=f"asch:d:{day_iso}")],
        ]
    )


def pair_html(ls: dict) -> str:
    head = f"🕐 Пара {ls['pair_no']}: {ls['start']}–{ls['end']}"
    if ls.get("lesson_type"):
        head += f" | {ls['lesson_type']}"
    lines = [f"<b>{su.esc(head)}</b>", f"{ls['emoji']} <b>{su.esc(ls['discipline'])}</b>"]
    tail = []
    if ls.get("teacher"):
        tail.append(su.esc(ls["teacher"]))
    if ls.get("room"):
        tail.append(f"ауд. {su.esc(ls['room'])}")
    if tail:
        lines.append(" • ".join(tail))
    return "\n".join(lines)


def disc_grid_kb(cb: str) -> InlineKeyboardMarkup:
    from ...keyboards import _grid

    items = [(f"{d['emoji']} {d['name']}", f"{cb}:{d['id']}") for d in db.all_disciplines()]
    return InlineKeyboardMarkup(inline_keyboard=_grid(items, 2))


def type_kb(cb: str) -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="ПР", callback_data=f"{cb}:ПР"), B(text="ЛЕК", callback_data=f"{cb}:ЛЕК"),
             B(text="ЛАБ", callback_data=f"{cb}:ЛАБ"), B(text="— без типа", callback_data=f"{cb}:none")],
        ]
    )


def pair_numbers_kb(day_iso: str, cb: str) -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    taken = {ls["pair_no"] for ls in db.day_lessons(day_iso)}
    rows = []
    row = []
    for n in range(1, 8):
        start, end = su.PAIR_TIMES[n - 1]
        mark = "✅" if n in taken else ""
        row.append(B(text=f"{mark}{n}\n{start}", callback_data=f"{cb}:{n}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([B(text="◀ Отмена", callback_data=f"asch:d:{day_iso}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:sch")
async def sch_admin_menu(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text("📅 <b>Управление расписанием</b>", reply_markup=sch_admin_kb())
    except TelegramBadRequest:
        pass


# ------------------------------------------------------------------ импорт JSON

@router.callback_query(F.data == "asch:imp")
async def sch_import_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SchImpSG.wait)
    await cb.answer()
    try:
        await cb.message.edit_text(
            "📥 <b>Импорт расписания из JSON</b>\n\n"
            "Отправьте файл <code>schedule.json</code> или вставьте текст JSON одним сообщением.\n"
            "<i>/cancel — отмена</i>"
        )
    except TelegramBadRequest:
        pass


@router.message(SchImpSG.wait, F.document)
async def sch_import_file(m: Message, state: FSMContext, bot):
    bio = BytesIO()
    await bot.download(m.document, destination=bio)
    text = bio.getvalue().decode("utf-8", errors="replace")
    await _do_import(m, state, text)


@router.message(SchImpSG.wait, F.text)
async def sch_import_text(m: Message, state: FSMContext):
    await _do_import(m, state, m.text or "")


async def _do_import(m: Message, state: FSMContext, text: str):
    await state.clear()
    try:
        report = su.import_schedule_json(text)
    except ValueError as e:
        await m.answer(f"❌ {su.esc(str(e))}\n\nПовторите: «📅 Расписание → 📥 Импорт JSON».")
        return
    days = ", ".join(su.fmt_dm(d) for d in report["day_list"][:12])
    if len(report["day_list"]) > 12:
        days += "…"
    lines = [
        "✅ <b>Импорт завершён</b>",
        "",
        f"Недель: {report['weeks']} • дней: {report['days']} • занятий: {report['lessons']}",
        f"Обновлённые дни: {days or '—'}",
    ]
    if report["warnings"]:
        warns = "\n".join(f"⚠️ {su.esc(w)}" for w in report["warnings"][:10])
        lines.append(f"\nПредупреждения:\n{warns}")
    await m.answer("\n".join(lines), reply_markup=sch_admin_kb())


# ------------------------------------------------------------------ календарь и дни

@router.callback_query(F.data == "asch:cal")
async def admin_calendar(cb: CallbackQuery):
    await cb.answer()
    d = su.today()
    kb = month_kb(d.year, d.month, "asch:", su.iso(d), ("◀ Управление расписанием", "adm:sch"))
    try:
        await cb.message.edit_text("🗓 Выберите день для редактирования:", reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("asch:cal:"))
async def admin_calendar_nav(cb: CallbackQuery):
    y, mth = cb.data.split(":")[2].split("-")
    kb = month_kb(int(y), int(mth), "asch:", su.iso(su.today()), ("◀ Управление расписанием", "adm:sch"))
    await cb.answer()
    try:
        await cb.message.edit_text("🗓 Выберите день для редактирования:", reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("asch:d:"))
async def admin_day(cb: CallbackQuery):
    day_iso = cb.data.split(":")[2]
    await cb.answer()
    try:
        await cb.message.edit_text(admin_day_view_html(day_iso), reply_markup=admin_day_kb(day_iso))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("asch:dn:"))
async def admin_day_nav(cb: CallbackQuery):
    parts = cb.data.split(":")
    d = date.fromisoformat(parts[2]) + timedelta(days=int(parts[3]))
    await cb.answer()
    try:
        await cb.message.edit_text(admin_day_view_html(d.isoformat()), reply_markup=admin_day_kb(d.isoformat()))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("asch:dx:"))
async def admin_day_delete(cb: CallbackQuery):
    day_iso = cb.data.split(":")[2]
    db.delete_day(day_iso)
    await cb.answer("Расписание удалено")
    try:
        await cb.message.edit_text(admin_day_view_html(day_iso), reply_markup=admin_day_kb(day_iso))
    except TelegramBadRequest:
        pass


# ------------------------------------------------------------------ редактор пары

@router.callback_query(F.data.startswith("asch:p:"))
async def pair_menu(cb: CallbackQuery):
    parts = cb.data.split(":")
    day_iso, pair_no = parts[2], int(parts[3])
    ls = get_pair(day_iso, pair_no)
    if ls is None:
        await cb.answer("Пара не найдена", show_alert=True)
        return
    await cb.answer()
    try:
        await cb.message.edit_text(pair_html(ls), reply_markup=pair_menu_kb(day_iso, pair_no))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("asch:pf:"))
async def pair_field(cb: CallbackQuery, state: FSMContext):
    """asch:pf:{iso}:{n}:{field} — единый диспетчер полей пары."""
    parts = cb.data.split(":")  # asch, pf, iso, n, field
    if len(parts) != 5:
        await cb.answer()
        return
    day_iso, pair_no, field = parts[2], parts[3], parts[4]
    if not pair_no.isdigit():
        await cb.answer()
        return
    await cb.answer()

    if field == "disc":
        await cb.message.edit_text(
            "📐 Выберите дисциплину:", reply_markup=disc_grid_kb(f"asch:pd:{day_iso}:{pair_no}")
        )
    elif field == "type":
        await cb.message.edit_text("🏷 Тип занятия:", reply_markup=type_kb(f"asch:pt:{day_iso}:{pair_no}"))
    elif field == "room":
        await state.set_state(SchEdSG.room)
        await state.update_data(iso=day_iso, pair_no=int(pair_no))
        await cb.message.edit_text("🚪 Введите аудиторию (или «-» чтобы убрать):")
    elif field == "time":
        taken_note = "\n".join(f"{i+1} — {s}–{e}" for i, (s, e) in enumerate(su.PAIR_TIMES))
        await cb.message.edit_text(
            f"🕐 Выберите номер пары (стандартное время):\n{taken_note}",
            reply_markup=pair_numbers_kb(day_iso, f"asch:pn:{day_iso}:{pair_no}"),
        )
    else:
        await cb.answer("Неизвестное поле", show_alert=True)


@router.callback_query(F.data.startswith("asch:pd:"))
async def pair_set_disc(cb: CallbackQuery):
    parts = cb.data.split(":")  # asch:pd:{iso}:{n}:{did}
    day_iso, pair_no, did = parts[2], int(parts[3]), int(parts[4])
    if db.discipline_by_id(did) is None:
        await cb.answer("Не найдена", show_alert=True)
        return
    db.ex("UPDATE schedule SET discipline_id=? WHERE date=? AND pair_no=?", (did, day_iso, pair_no))
    await cb.answer("Обновлено")
    ls = get_pair(day_iso, pair_no)
    await cb.message.edit_text(pair_html(ls), reply_markup=pair_menu_kb(day_iso, pair_no))


@router.callback_query(F.data.startswith("asch:pt:"))
async def pair_set_type(cb: CallbackQuery):
    parts = cb.data.split(":")  # asch:pt:{iso}:{n}:{тип}
    day_iso, pair_no, lt = parts[2], int(parts[3]), parts[4]
    db.ex(
        "UPDATE schedule SET lesson_type=? WHERE date=? AND pair_no=?",
        (None if lt == "none" else lt, day_iso, pair_no),
    )
    await cb.answer("Обновлено")
    ls = get_pair(day_iso, pair_no)
    await cb.message.edit_text(pair_html(ls), reply_markup=pair_menu_kb(day_iso, pair_no))


@router.message(SchEdSG.room, F.text & ~F.text.startswith("/"))
async def pair_set_room(m: Message, state: FSMContext):
    data = await state.get_data()
    room = (m.text or "").strip()
    db.ex(
        "UPDATE schedule SET room=? WHERE date=? AND pair_no=?",
        (None if room in ("-", "—") else room, data["iso"], data["pair_no"]),
    )
    await state.clear()
    ls = get_pair(data["iso"], data["pair_no"])
    await m.answer("✅ Сохранено.")
    await m.answer(pair_html(ls), reply_markup=pair_menu_kb(data["iso"], data["pair_no"]))


def _time_custom_kb(day_iso: str, pair_no: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Своё время (ЧЧ:ММ-ЧЧ:ММ)", callback_data=f"asch:pc:{day_iso}:{pair_no}")],
            [InlineKeyboardButton(text="◀ Назад", callback_data=f"asch:p:{day_iso}:{pair_no}")],
        ]
    )


@router.callback_query(F.data.startswith("asch:pn:"))
async def pair_set_number(cb: CallbackQuery):
    parts = cb.data.split(":")  # asch:pn:{iso}:{старый}:{новый}
    day_iso, old_no, new_no = parts[2], int(parts[3]), int(parts[4])
    if new_no < 1 or new_no > 7:
        await cb.answer("Номер 1–7", show_alert=True)
        return
    if get_pair(day_iso, new_no) is not None:
        await cb.answer("Этот номер уже занят", show_alert=True)
        return
    start, end = su.PAIR_TIMES[new_no - 1]
    db.ex(
        "UPDATE schedule SET pair_no=?, start=?, end=? WHERE date=? AND pair_no=?",
        (new_no, start, end, day_iso, old_no),
    )
    await cb.answer("Обновлено")
    ls = get_pair(day_iso, new_no)
    await cb.message.edit_text(pair_html(ls), reply_markup=pair_menu_kb(day_iso, new_no))


@router.callback_query(F.data.startswith("asch:pc:"))
async def pair_time_custom(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")  # asch:pc:{iso}:{n}
    await state.set_state(SchEdSG.time)
    await state.update_data(iso=parts[2], pair_no=int(parts[3]))
    await cb.answer()
    await cb.message.edit_text("✍️ Введите время в формате ЧЧ:ММ-ЧЧ:ММ (например 11:50-13:20):")


@router.message(SchEdSG.time, F.text & ~F.text.startswith("/"))
async def pair_set_time(m: Message, state: FSMContext):
    raw = (m.text or "").strip().replace("–", "-").replace(" ", "")
    if "-" not in raw:
        await m.answer("⚠️ Формат: ЧЧ:ММ-ЧЧ:ММ (например 11:50-13:20):")
        return
    s, e = raw.split("-", 1)
    ts_, te = su.parse_hm(s), su.parse_hm(e)
    if ts_ is None or te is None or ts_ >= te:
        await m.answer("⚠️ Неверное время. Формат: ЧЧ:ММ-ЧЧ:ММ:")
        return
    data = await state.get_data()
    db.ex(
        "UPDATE schedule SET start=?, end=? WHERE date=? AND pair_no=?",
        (s, e, data["iso"], data["pair_no"]),
    )
    await state.clear()
    ls = get_pair(data["iso"], data["pair_no"])
    await m.answer("✅ Сохранено.")
    await m.answer(pair_html(ls), reply_markup=pair_menu_kb(data["iso"], data["pair_no"]))


@router.callback_query(F.data.startswith("asch:px:"))
async def pair_delete(cb: CallbackQuery):
    parts = cb.data.split(":")
    day_iso, pair_no = parts[2], int(parts[3])
    db.ex("DELETE FROM schedule WHERE date=? AND pair_no=?", (day_iso, pair_no))
    await cb.answer("Пара удалена")
    await cb.message.edit_text(admin_day_view_html(day_iso), reply_markup=admin_day_kb(day_iso))


# ------------------------------------------------------------------ добавление пары

@router.callback_query(F.data.startswith("asch:pa:"))
async def add_pair_start(cb: CallbackQuery):
    day_iso = cb.data.split(":")[2]
    await cb.answer()
    await cb.message.edit_text(
        "➕ Выберите номер пары (✅ — занято):", reply_markup=pair_numbers_kb(day_iso, f"asch:pan:{day_iso}")
    )


@router.callback_query(F.data.startswith("asch:pan:"))
async def add_pair_number(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")  # asch:pan:{iso}:{n}
    day_iso, n = parts[2], int(parts[3])
    if get_pair(day_iso, n) is not None:
        await cb.answer("Этот номер уже занят", show_alert=True)
        return
    await state.set_state(SchEdSG.add_room)
    await state.update_data(iso=day_iso, new_no=n)
    await cb.answer()
    await cb.message.edit_text("📐 Выберите дисциплину:", reply_markup=disc_grid_kb(f"asch:pad:{day_iso}:{n}"))


@router.callback_query(F.data.startswith("asch:pad:"))
async def add_pair_disc(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")  # asch:pad:{iso}:{n}:{did}
    day_iso, n, did = parts[2], int(parts[3]), int(parts[4])
    if db.discipline_by_id(did) is None:
        await cb.answer("Не найдена", show_alert=True)
        return
    await state.update_data(new_disc=did)
    await cb.answer()
    await cb.message.edit_text("🏷 Тип занятия:", reply_markup=type_kb(f"asch:pat:{day_iso}:{n}"))


@router.callback_query(F.data.startswith("asch:pat:"))
async def add_pair_type(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")  # asch:pat:{iso}:{n}:{тип}
    lt = parts[4]
    await state.update_data(new_type=None if lt == "none" else lt)
    await cb.answer()
    await cb.message.edit_text(
        "🚪 Введите аудиторию (или «-» если нет):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[])
    )


@router.message(SchEdSG.add_room, F.text & ~F.text.startswith("/"))
async def add_pair_room(m: Message, state: FSMContext):
    data = await state.get_data()
    room = (m.text or "").strip()
    n = data["new_no"]
    start, end = su.PAIR_TIMES[n - 1]
    db.ins(
        "INSERT INTO schedule(date,pair_no,start,end,discipline_id,lesson_type,room) VALUES(?,?,?,?,?,?,?)",
        (data["iso"], n, start, end, data["new_disc"], data["new_type"], None if room in ("-", "—") else room),
    )
    await state.clear()
    await m.answer("✅ Пара добавлена.")
    await m.answer(admin_day_view_html(data["iso"]), reply_markup=admin_day_kb(data["iso"]))
