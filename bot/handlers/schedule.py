"""Раздел «Расписание» для студентов."""
from datetime import date

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from .. import db
from ..keyboards import day_nav_kb, month_kb, sch_menu_kb
from ..services import schedule_utils as su

router = Router()


async def show_day(cb: CallbackQuery, day_iso: str):
    n = su.now()
    with_statuses = day_iso == su.iso(n.date())
    text = su.day_view_html(day_iso, n, with_statuses)
    if not text:
        d = date.fromisoformat(day_iso)
        extra = " (воскресенье — выходной)" if d.weekday() == 6 else ""
        text = f"📭 <b>На этот день ещё нет расписания.</b>{extra}"
    notice = db.kv_get(f"day_notice_{day_iso}", "")
    if notice:
        text = f"⚠️ <b>Метка дня:</b> {su.esc(notice)}\n\n{text}"
    try:
        await cb.message.edit_text(text, reply_markup=day_nav_kb(day_iso))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "sch")
async def sch_menu(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text(
            "📅 <b>Расписание</b>\n\nВыберите период:", reply_markup=sch_menu_kb()
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("sch:d:"))
async def sch_day(cb: CallbackQuery):
    day_iso = cb.data.split(":")[2]
    await cb.answer()
    await show_day(cb, day_iso)


@router.callback_query(F.data == "sch:cal")
async def sch_calendar(cb: CallbackQuery):
    await cb.answer()
    d = su.today()
    kb = month_kb(d.year, d.month, "sch:", su.iso(d), ("🏠 Главное меню", "home"))
    try:
        await cb.message.edit_text("🗓 <b>Выберите день</b>\n✳️ — сегодня", reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("sch:cal:"))
async def sch_calendar_nav(cb: CallbackQuery):
    y, m = cb.data.split(":")[2].split("-")
    await cb.answer()
    kb = month_kb(int(y), int(m), "sch:", su.iso(su.today()), ("🏠 Главное меню", "home"))
    try:
        await cb.message.edit_text("🗓 <b>Выберите день</b>\n✳️ — сегодня", reply_markup=kb)
    except TelegramBadRequest:
        pass
