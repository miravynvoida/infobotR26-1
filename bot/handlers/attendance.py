"""Ответы студентов на опрос о посещаемости."""
import json
from datetime import date, datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from .. import db
from ..keyboards import attendance_kb, attendance_pick_kb
from ..services import schedule_utils as su
from ..states import AttSG

router = Router()


def _parse_day(payload: str) -> str:
    d = payload.strip()
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"


@router.callback_query(F.data.regexp_match(r"^att:(full|none|sick):\d{8}$"))
async def att_answer(cb: CallbackQuery, student: dict):
    status = cb.data.split(":")[1]
    day = _parse_day(cb.data.split(":")[2])
    if day != su.iso(su.today()):
        await cb.answer("Это опрос за прошедший день", show_alert=True)
        return
    db.set_attendance(day, student["id"], status, [], su.ts())
    await cb.answer()
    texts = {
        "full": "✅ Записано: вы будете сегодня на всех парах. Хорошего дня!",
        "none": "❌ Записано: вас сегодня не будет.",
        "sick": "🤒 Выздоровления! Отметила вас болеющим (видят только староста и зам).",
    }
    try:
        await cb.message.edit_text(
            f"<b>Посещаемость — {su.fmt_dmy(day)}</b>\n\n{texts[status]}\n\n"
            "<i>Ответ можно изменить, нажав кнопку ниже, до конца дня.</i>",
            reply_markup=attendance_kb(day),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp_match(r"^att:partial:\d{8}$"))
async def att_partial(cb: CallbackQuery, state: FSMContext):
    day = _parse_day(cb.data.split(":")[2])
    if day != su.iso(su.today()):
        await cb.answer("Это опрос за прошедший день", show_alert=True)
        return
    lessons = db.day_lessons(day)
    if not lessons:
        await cb.answer("Сегодня пар нет", show_alert=True)
        return
    await state.set_state(AttSG.pick)
    await state.update_data(att_date=day, att_missing=[])
    await cb.answer()
    try:
        await cb.message.edit_text(
            "⚖️ <b>Отметьте пары, которые вы ПРОПУСТИТЕ</b> (нажимая на них), затем «✅ Подтвердить»:",
            reply_markup=attendance_pick_kb(day, lessons, set()),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(AttSG.pick, F.data.regexp_match(r"^att:t:\d+$"))
async def att_toggle(cb: CallbackQuery, state: FSMContext):
    pair_no = int(cb.data.split(":")[2])
    data = await state.get_data()
    day = data["att_date"]
    missing = set(data.get("att_missing") or [])
    missing.symmetric_difference_update({pair_no})
    await state.update_data(att_missing=sorted(missing))
    await cb.answer("❌ Пропустите" if pair_no in missing else "▫️ Будете")
    lessons = db.day_lessons(day)
    try:
        await cb.message.edit_text(
            "⚖️ <b>Отметьте пары, которые вы ПРОПУСТИТЕ</b>, затем «✅ Подтвердить»:",
            reply_markup=attendance_pick_kb(day, lessons, missing),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(AttSG.pick, F.data == "att:ok")
async def att_confirm(cb: CallbackQuery, state: FSMContext, student: dict):
    data = await state.get_data()
    day = data["att_date"]
    missing = sorted(data.get("att_missing") or [])
    await state.clear()
    db.set_attendance(day, student["id"], "partial", missing, su.ts())
    await cb.answer()
    if missing:
        pairs = ", ".join(str(p) for p in missing)
        text = (
            f"⚖️ Записано: вы будете не на всех парах.\n"
            f"Пропустите пары: <b>{pairs}</b>."
        )
    else:
        text = "✅ Записано: вы будете на всех парах."
    try:
        await cb.message.edit_text(f"<b>Посещаемость — {su.fmt_dmy(day)}</b>\n\n{text}")
    except TelegramBadRequest:
        pass
