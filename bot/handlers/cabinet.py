"""Личный кабинет: статистика и настройки уведомлений."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import db
from ..keyboards import cab_kb, minutes_kb, times_kb
from ..services import schedule_utils as su
from ..states import CabSG

router = Router()


def cab_html(student: dict) -> str:
    st = db.student_stats(student["id"])
    return "\n".join(
        [
            f"👤 <b>Личный кабинет</b>\n{su.esc(student['fio'])}",
            "",
            f"📊 Средний балл: <b>{su.fmt_avg(st['avg'])}</b> (оценок: {st['total']})",
            f"❌ Пропусков (Н): <b>{st['h']}</b>",
            f"🤒 По болезни (Б): <b>{st['b']}</b>",
            f"⏰ Опозданий (О): <b>{st['o']}</b>",
            "",
            "⚙️ <b>Уведомления</b>",
            "🔒 Важные, новые ДЗ и посещаемость — всегда включены.",
        ]
    )


async def render(cb: CallbackQuery, student: dict):
    s = db.get_settings(student["id"])
    try:
        await cb.message.edit_text(cab_html(student), reply_markup=cab_kb(s))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "cab")
async def cab_menu(cb: CallbackQuery, student: dict):
    await cb.answer()
    await render(cb, student)


@router.callback_query(F.data == "cab:np:tgl")
async def np_toggle(cb: CallbackQuery, student: dict):
    s = db.get_settings(student["id"])
    db.update_settings(student["id"], next_pair=0 if s["next_pair"] else 1)
    await cb.answer("🔔 Напоминания о парах: ВЫКЛ" if s["next_pair"] else "🔔 Напоминания о парах: ВКЛ")
    await render(cb, student)


@router.callback_query(F.data == "cab:np:menu")
async def np_menu(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text("⏱ За сколько минут напоминать о паре?", reply_markup=minutes_kb())
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp_match(r"^cab:np:\d+$"))
async def np_set(cb: CallbackQuery, student: dict):
    minutes = int(cb.data.split(":")[2])
    db.update_settings(student["id"], next_pair=1, next_pair_min=minutes)
    await cb.answer(f"✅ Буду напоминать за {minutes} мин")
    await render(cb, student)


@router.callback_query(F.data == "cab:tm:tgl")
async def tm_toggle(cb: CallbackQuery, student: dict):
    s = db.get_settings(student["id"])
    db.update_settings(student["id"], tomorrow=0 if s["tomorrow"] else 1)
    await cb.answer("📅 Расписание на завтра: ВЫКЛ" if s["tomorrow"] else "📅 Расписание на завтра: ВКЛ")
    await render(cb, student)


@router.callback_query(F.data == "cab:tm:menu")
async def tm_menu(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text("🕐 В какое время присылать расписание на завтра?", reply_markup=times_kb())
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp_match(r"^cab:tm:\d{2}:\d{2}$"))
async def tm_set(cb: CallbackQuery, student: dict):
    parts = cb.data.split(":")
    val = f"{parts[2]}:{parts[3]}"
    db.update_settings(student["id"], tomorrow=1, tomorrow_time=val)
    await cb.answer(f"✅ Буду присылать в {val}")
    await render(cb, student)


@router.callback_query(F.data == "cab:tm:c")
async def tm_custom(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(CabSG.tmrw_time)
    try:
        await cb.message.edit_text("✍️ Введите время в формате ЧЧ:ММ (например, 18:30):")
    except TelegramBadRequest:
        pass


@router.message(CabSG.tmrw_time, F.text)
async def tm_custom_input(m: Message, state: FSMContext, student: dict, is_admin: bool):
    tm = su.parse_hm((m.text or "").strip())
    if tm is None:
        await m.answer("⚠️ Неверный формат. Введите время как ЧЧ:ММ, например 18:30:")
        return
    db.update_settings(student["id"], tomorrow=1, tomorrow_time=tm.strftime("%H:%M"))
    await state.clear()
    await m.answer(f"✅ Расписание на завтра будет приходить в {tm.strftime('%H:%M')}.")
    s = db.get_settings(student["id"])
    await m.answer(cab_html(student), reply_markup=cab_kb(s))


@router.callback_query(F.data == "cab:ms:tgl")
async def ms_toggle(cb: CallbackQuery, student: dict):
    s = db.get_settings(student["id"])
    db.update_settings(student["id"], misc=0 if s["misc"] else 1)
    await cb.answer("💤 Прочие уведомления: ВЫКЛ" if s["misc"] else "💤 Прочие уведомления: ВКЛ")
    await render(cb, student)
