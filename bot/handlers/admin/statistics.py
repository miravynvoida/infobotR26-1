"""Обзор и статистика + синхронизация оценок."""
import asyncio

import os

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from ... import config
from ...states import MntSG

from ... import db
from ...services import maintenance as mnt
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
    B = InlineKeyboardButton
    m = mnt.maintenance_state()
    rows = [
        [B(text="🔄 Синхронизировать оценки", callback_data="adm:sync")],
        [
            B(
                text=f"🛠 Тех. работы: {'ВКЛ' if m['on'] else 'выкл'}",
                callback_data="adm:mnt",
            ),
            B(
                text=f"⚠️ Контрольная: {'ВКЛ' if mnt.exam_week_state() else 'выкл'}",
                callback_data="adm:exam",
            ),
        ],
        [B(text="💾 Бэкап базы", callback_data="adm:backup"), B(text="📥 Загрузить базу", callback_data="adm:restore")],
        [B(text="◀ Админ-панель", callback_data="adm")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:st")
async def stats_view(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text(stats_html(), reply_markup=stats_kb())
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "adm:mnt")
async def maintenance_toggle(cb: CallbackQuery, state: FSMContext):
    m = mnt.maintenance_state()
    if m["on"]:
        mnt.stop_maintenance()
        await cb.answer("Тех. работы выключены")
        await cb.message.edit_text(stats_html(), reply_markup=stats_kb())
        return
    await state.set_state(MntSG.until)
    await cb.answer()
    await cb.message.edit_text(
        "🛠 Введите дату и время окончания тех. работ в формате <code>DD.MM.YYYY ЧЧ:ММ</code>\n"
        "или отправьте «-», чтобы включить бессрочно.\n<i>/cancel — отмена</i>"
    )


@router.callback_query(F.data == "adm:exam")
async def exam_week_toggle(cb: CallbackQuery):
    new = not mnt.exam_week_state()
    mnt.set_exam_week(new)
    await cb.answer("Контрольная неделя включена" if new else "Контрольная неделя выключена")
    await cb.message.edit_text(stats_html(), reply_markup=stats_kb())


@router.callback_query(F.data == "adm:backup")
async def backup_db(cb: CallbackQuery):
    import os

    from aiogram.types import FSInputFile

    if not os.path.exists(config.cfg.db_path):
        await cb.answer("Файл базы не найден", show_alert=True)
        return
    await cb.answer()
    db.checkpoint()
    await cb.message.answer_document(
        FSInputFile(config.cfg.db_path, filename=f"r26-1-backup-{su.iso(su.today())}.db"),
        caption="💾 Бэкап базы. Храните в надёжном месте.",
    )


@router.callback_query(F.data == "adm:restore")
async def restore_db_prompt(cb: CallbackQuery, state: FSMContext):
    await state.set_state(MntSG.restore)
    await cb.answer()
    await cb.message.edit_text(
        "📥 Отправьте файл базы <code>.db</code> — он заменит текущую.\n"
        "<b>Действие серьёзное:</b> все данные станут как в файле.\n<i>/cancel — отмена</i>"
    )


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


@router.message(MntSG.until, F.text & ~F.text.startswith("/"))
async def maintenance_until_input(m, state):
    text = (m.text or "").strip()
    if text in ("-", "—"):
        mnt.set_maintenance(None)
        await state.clear()
        await m.answer("🛠 Тех. работы включены <b>бессрочно</b>. Выключить — в статистике.", reply_markup=stats_kb())
        return
    dt = su.parse_dt(text)
    if dt is None:
        await m.answer("⚠️ Формат: DD.MM.YYYY ЧЧ:ММ (например, 25.10.2026 18:00) или «-»:")
        return
    mnt.set_maintenance(dt)
    await state.clear()
    await m.answer(
        f"🛠 Тех. работы включены до <b>{dt.strftime('%d.%m.%Y %H:%M')}</b>.",
        reply_markup=stats_kb(),
    )


@router.message(MntSG.restore, F.document)
async def restore_db_file(m, state):
    import tempfile

    if not (m.document.file_name or "").endswith(".db"):
        await m.answer("⚠️ Нужен файл .db. Попробуйте ещё раз или /cancel.")
        return
    bio = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    await m.bot.download(m.document, destination=bio)
    bio.close()
    try:
        db.swap_database(bio.name)
        await state.clear()
        await m.answer("✅ База заменена. Данные — из вашего файла.", reply_markup=stats_kb())
    except Exception as e:
        await state.clear()
        await m.answer(f"❌ Не удалось заменить базу: {e}", reply_markup=stats_kb())
