"""Обзор и статистика + синхронизация оценок."""
import asyncio

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from ... import db
from ...services import schedule_utils as su
from ...services.grades import sync_grades
from .panel import admin_panel_kb

router = Router()


def stats_html() -> str:
    students = db.all_students()
    authed = [s for s in students if s["tg_id"]]
    day = su.iso(su.today())
    att = db.day_attendance(day)
    last_sync = db.kv_get("last_grades_sync")
    if last_sync:
        last_sync = f"{last_sync[8:10]}.{last_sync[5:7]} {last_sync[11:16]}"
    else:
        last_sync = "ещё не было"
    return "\n".join(
        [
            "📊 <b>Обзор и статистика</b>",
            "",
            f"👥 Студентов: <b>{len(students)}</b> (авторизовано: {len(authed)})",
            f"📐 Дисциплин: <b>{len(db.all_disciplines())}</b>",
            f"📅 Дней с расписанием: <b>{len(db.schedule_dates())}</b>",
            f"📚 ДЗ: активных <b>{len(db.active_homework())}</b> • в архиве <b>{len(db.archived_homework())}</b>",
            f"📖 Учебников: <b>{len(db.all_textbooks())}</b>",
            f"🔁 Оценки синхронизированы: {last_sync}",
            f"📋 Сегодня ответили о посещаемости: {len(att)}/{len(authed)}",
        ]
    )


def stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Синхронизировать оценки", callback_data="adm:sync")],
            [InlineKeyboardButton(text="◀ Админ-панель", callback_data="adm")],
        ]
    )


@router.callback_query(F.data == "adm:st")
async def stats_view(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text(stats_html(), reply_markup=stats_kb())
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "adm:sync")
async def grades_sync(cb: CallbackQuery):
    await cb.answer("⏳ Синхронизирую…")
    report = await asyncio.to_thread(sync_grades)
    if not report.get("ok"):
        text = f"❌ <b>Ошибка синхронизации</b>\n\n{su.esc(report.get('error', ''))}"
    else:
        parts = [
            "✅ <b>Оценки синхронизированы</b>",
            "",
            f"Листов обработано: {report['sheets']}",
            f"Отметок занесено: {report['marks']}",
        ]
        if report["unknown_sheets"]:
            parts.append(f"⚠️ Листы без дисциплины: {', '.join(su.esc(x) for x in report['unknown_sheets'])}")
        if report["unknown_fio"]:
            parts.append(f"⚠️ Не распознаны ФИО: {', '.join(su.esc(x) for x in report['unknown_fio'])}")
        if report["skipped_columns"]:
            parts.append(f"⚠️ Пропущено столбцов без даты: {report['skipped_columns']}")
        text = "\n".join(parts)
    try:
        await cb.message.edit_text(stats_html() + "\n\n" + text, reply_markup=stats_kb())
    except TelegramBadRequest:
        await cb.message.answer(text)
