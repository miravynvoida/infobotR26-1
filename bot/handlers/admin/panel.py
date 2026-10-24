"""Корень админ-панели + повторный опрос посещаемости."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from ... import db
from ...keyboards import attendance_kb, attendance_pair_kb
from ...services import schedule_utils as su
from ...services.jobs import send_attendance_ask

router = Router()


def admin_panel_kb() -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="📚 ДЗ", callback_data="adm:hw"), B(text="📅 Расписание", callback_data="adm:sch")],
            [B(text="📖 Учебники", callback_data="adm:tb"), B(text="📊 Обзор и статистика", callback_data="adm:st")],
            [B(text="👥 Студенты", callback_data="adm:studs"), B(text="📐 Дисциплины", callback_data="adm:disc")],
            [B(text="📋 Опрос посещаемости", callback_data="adm:ask")],
            [B(text="📣 Уведомление всем", callback_data="adm:bc")],
            [B(text="🏠 Главное меню", callback_data="home")],
        ]
    )


@router.callback_query(F.data == "adm")
async def admin_root(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text("🛠 <b>Админ-панель</b>\n\nВыберите раздел:", reply_markup=admin_panel_kb())
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "adm:ask")
async def admin_ask_menu(cb: CallbackQuery):
    day = su.iso(su.today())
    lessons = db.day_lessons(day)
    B = InlineKeyboardButton
    rows = [[B(text="🌍 Весь день (повторно всем)", callback_data="adm:ask:day")]]
    for ls in lessons:
        rows.append(
            [B(text=f"{ls['pair_no']} • {ls['start']} {ls['discipline']}", callback_data=f"adm:ask:p:{ls['pair_no']}")]
        )
    rows.append([B(text="◀ Админ-панель", callback_data="adm")])
    text = (
        "📋 <b>Повторный опрос посещаемости</b>\n\n"
        "Придёт <b>всем</b> авторизованным — даже тем, кто уже отметился "
        "(удобно для проверки и напоминания).\n\n"
        + (f"Сегодня пар: {len(lessons)}." if lessons else "⚠️ Сегодня расписания нет — доступен только опрос за день.")
    )
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "adm:ask:day")
async def admin_ask_day(cb: CallbackQuery):
    day = su.iso(su.today())
    lessons = db.day_lessons(day)
    if not lessons:
        await cb.answer("Сегодня пар нет", show_alert=True)
        return
    sent = 0
    muted = db.muted_tg_ids()
    for st in db.authorized_students():
        if st["tg_id"] in muted:
            continue
        try:
            await send_attendance_ask(cb.bot, st, day, lessons[0]["start"])
            sent += 1
        except Exception:
            continue
    await cb.answer("Разослано")
    try:
        await cb.message.edit_text(
            f"📋 Опрос за весь день разослан: <b>{sent}</b> получателям.", reply_markup=admin_panel_kb()
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("adm:ask:p:"))
async def admin_ask_pair(cb: CallbackQuery):
    raw = cb.data.split(":")[3]
    if not raw.isdigit():
        await cb.answer()
        return
    pair_no = int(raw)
    day = su.iso(su.today())
    ls = next((x for x in db.day_lessons(day) if x["pair_no"] == pair_no), None)
    if ls is None:
        await cb.answer("Пара не найдена", show_alert=True)
        return
    sent = 0
    muted = db.muted_tg_ids()
    for st in db.authorized_students():
        if st["tg_id"] in muted:
            continue
        try:
            await cb.bot.send_message(
                st["tg_id"],
                f"📋 <b>Будете ли вы на паре {pair_no}?</b>\n"
                f"{ls['emoji']} <b>{su.esc(ls['discipline'])}</b> · {ls['start']}–{ls['end']}"
                + (f" · ауд. {su.esc(ls['room'])}" if ls.get("room") else ""),
                reply_markup=attendance_pair_kb(day, pair_no),
            )
            sent += 1
        except Exception:
            continue
    await cb.answer("Разослано")
    try:
        await cb.message.edit_text(
            f"📋 Опрос по паре {pair_no} ({su.esc(ls['discipline'])}) разослан: <b>{sent}</b> получателям.",
            reply_markup=admin_panel_kb(),
        )
    except TelegramBadRequest:
        pass
