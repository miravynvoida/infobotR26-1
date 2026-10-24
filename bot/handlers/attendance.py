"""Ответы студентов на опрос о посещаемости (весь день до конца последней пары).

Порядок регистрации важен: специфичные кнопки (att:t:, att:ok, att:partial:)
раньше, generic «att:» — последним.
"""
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


def _window_ok(cb_day: str) -> str | None:
    """Ответ можно менять сегодня и только до конца последней пары. Возвращает текст ошибки."""
    if cb_day != su.iso(su.today()):
        return "Это опрос за прошедший день"
    lessons = db.day_lessons(cb_day)
    if not lessons:
        return "Сегодня пар нет"
    if su.now() > su.dt_on(cb_day, lessons[-1]["end"]):
        return "Пары уже закончились — отметиться нельзя"
    return None


@router.callback_query(AttSG.pick, F.data.startswith("att:t:"))
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
    err = _window_ok(day)
    if err:
        await cb.answer(err, show_alert=True)
        return
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


@router.callback_query(F.data.startswith("att:partial:"))
async def att_partial(cb: CallbackQuery, state: FSMContext):
    day = _parse_day(cb.data.split(":")[2])
    err = _window_ok(day)
    if err:
        await cb.answer(err, show_alert=True)
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


# generic «att:{status}:{дата}» — последним
@router.callback_query(F.data.startswith("att:"))
async def att_answer(cb: CallbackQuery, student: dict, state: FSMContext):
    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer()
        return
    status, day_raw = parts[1], parts[2]
    if status not in ("full", "none", "sick") or not day_raw.isdigit() or len(day_raw) != 8:
        await cb.answer()
        return

    day = _parse_day(day_raw)
    err = _window_ok(day)
    if err:
        await cb.answer(err, show_alert=True)
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
            "<i>Ответ можно изменить, нажав кнопку ниже, до конца последней пары.</i>",
            reply_markup=attendance_kb(day),
        )
    except TelegramBadRequest:
        pass
