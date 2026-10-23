"""/start, вход по ФИО + коду, первичная настройка (онбординг)."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import config, db
from ..keyboards import (
    onb_minutes_kb,
    onb_theme_kb,
    onb_times_kb,
    onb_yes_no,
)
from ..services import schedule_utils as su
from ..states import AuthSG, OnbSG

router = Router()


@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext, student: dict | None):
    await state.clear()
    if student:
        await send_main(m, student)
        return
    await m.answer(
        f"👋 Привет!\n\n"
        f"Это информационный бот группы <b>{su.esc(config.cfg.group_name)}</b>. "
        "Доступ только для студентов группы.\n\n"
        "Для входа введите ваше <b>ФИО полностью</b>, как в списке группы.\n"
        "<i>Например: Иванов Пётр Сергеевич</i>"
    )
    await state.set_state(AuthSG.fio)


@router.message(AuthSG.fio, F.text & ~F.text.startswith("/"))
async def auth_fio(m: Message, state: FSMContext):
    fio = " ".join((m.text or "").split())
    st = db.student_by_fio(fio)
    if not st:
        await m.answer(
            "😦 Такое ФИО не найдено в списках группы.\n"
            "Проверьте написание и введите ещё раз, либо обратитесь к старосте.\n"
            "<i>Отмена — /cancel</i>"
        )
        return
    if st["tg_id"]:
        await m.answer(
            "⛔ Этот студент уже авторизован в боте с другого аккаунта.\n"
            "Если это действительно вы — обратитесь к старосте или заму (сбросят привязку)."
        )
        await state.clear()
        return
    await state.update_data(sid=st["id"])
    await m.answer(
        f"✅ Найдено: <b>{su.esc(st['fio'])}</b>\n\n"
        "Теперь введите <b>индивидуальный код входа</b> (его выдаёт староста или зам старосты)."
    )
    await state.set_state(AuthSG.code)


@router.message(AuthSG.code, F.text & ~F.text.startswith("/"))
async def auth_code(m: Message, state: FSMContext):
    data = await state.get_data()
    st = db.student_by_id(data["sid"])
    if st is None:
        await state.clear()
        await m.answer("⚠️ Сессия входа устарела. Нажмите /start.")
        return
    if (m.text or "").strip().upper() != st["code"].upper():
        await m.answer("❌ Неверный код. Попробуйте ещё раз.\n<i>Отмена — /cancel</i>")
        return
    db.link_tg(st["id"], m.from_user.id)
    db.get_settings(st["id"])
    await m.answer(
        f"🎉 Вы успешно авторизованы, <b>{su.esc(su.short_name(st['fio']))}</b>!\n\n"
        "Осталась быстрая настройка уведомлений — 4 шага (по умолчанию всё включено, "
        "потом можно менять в «👤 Кабинет»)."
    )
    await m.answer(
        "1️⃣ Присылать напоминание <b>перед каждой парой</b>?",
        reply_markup=onb_yes_no("onb:p"),
    )
    await state.set_state(OnbSG.pair)


# ---------------------------------------------------------------- онбординг

@router.callback_query(OnbSG.pair, F.data.startswith("onb:p:"))
async def onb_pair(cb: CallbackQuery, state: FSMContext):
    on = cb.data == "onb:p:1"
    await state.update_data(next_pair=1 if on else 0)
    if on:
        await cb.message.edit_text("⏱ За сколько минут напоминать?", reply_markup=onb_minutes_kb())
        await state.set_state(OnbSG.pair)
        await cb.answer()
        return
    await cb.message.edit_text("2️⃣ Присылать расписание на завтра?", reply_markup=onb_yes_no("onb:t"))
    await state.set_state(OnbSG.tmrw)
    await cb.answer()


@router.callback_query(OnbSG.pair, F.data.startswith("onb:pm:"))
async def onb_pair_min(cb: CallbackQuery, state: FSMContext):
    minutes = int(cb.data.split(":")[2])
    await state.update_data(next_pair=1, next_pair_min=minutes)
    await cb.message.edit_text("2️⃣ Присылать расписание на завтра?", reply_markup=onb_yes_no("onb:t"))
    await state.set_state(OnbSG.tmrw)
    await cb.answer()


@router.callback_query(OnbSG.tmrw, F.data.startswith("onb:t:"))
async def onb_tmrw(cb: CallbackQuery, state: FSMContext):
    if cb.data == "onb:t:1":
        await cb.message.edit_text("🕐 В какое время присылать?", reply_markup=onb_times_kb())
        await cb.answer()
        return
    await state.update_data(tomorrow=0)
    await cb.message.edit_text("3️⃣ Прочие уведомления (обновления и т.п.)?", reply_markup=onb_yes_no("onb:m"))
    await state.set_state(OnbSG.misc)
    await cb.answer()


@router.callback_query(OnbSG.tmrw, F.data.startswith("onb:tt:"))
async def onb_tmrw_time(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":")[2]
    if val == "c":
        await state.set_state(OnbSG.tmrw_time)
        await cb.message.edit_text("✍️ Введите время в формате ЧЧ:ММ (например, 18:30):")
        await cb.answer()
        return
    await state.update_data(tomorrow=1, tomorrow_time=val)
    await cb.message.edit_text("3️⃣ Прочие уведомления (обновления и т.п.)?", reply_markup=onb_yes_no("onb:m"))
    await state.set_state(OnbSG.misc)
    await cb.answer()


@router.message(OnbSG.tmrw_time, F.text)
async def onb_tmrw_time_input(m: Message, state: FSMContext):
    tm = su.parse_hm((m.text or "").strip())
    if tm is None:
        await m.answer("⚠️ Неверный формат. Введите время как ЧЧ:ММ, например 18:30:")
        return
    await state.update_data(tomorrow=1, tomorrow_time=tm.strftime("%H:%M"))
    await m.answer("3️⃣ Прочие уведомления (обновления и т.п.)?", reply_markup=onb_yes_no("onb:m"))
    await state.set_state(OnbSG.misc)


@router.callback_query(OnbSG.misc, F.data.startswith("onb:m:"))
async def onb_misc(cb: CallbackQuery, state: FSMContext):
    await state.update_data(misc=1 if cb.data == "onb:m:1" else 0)
    await cb.message.edit_text(
        "4️⃣ Тема мини-приложения «Дневник студента»:",
        reply_markup=onb_theme_kb(),
    )
    await state.set_state(OnbSG.theme)
    await cb.answer()


@router.callback_query(OnbSG.theme, F.data.startswith("onb:th:"))
async def onb_theme(cb: CallbackQuery, state: FSMContext, student: dict):
    theme = cb.data.split(":")[2]
    data = await state.get_data()
    db.update_settings(
        student["id"],
        next_pair=data.get("next_pair", 1),
        next_pair_min=data.get("next_pair_min", 30),
        tomorrow=data.get("tomorrow", 1),
        tomorrow_time=data.get("tomorrow_time", "19:00"),
        misc=data.get("misc", 1),
        theme=theme,
    )
    await cb.message.edit_text(
        "✅ <b>Настройка завершена!</b>\n\n"
        "🔒 Напоминания о посещаемости, важные оповещения и новые ДЗ "
        "приходят всегда — их отключить нельзя."
    )
    await state.clear()
    from .menu import send_main as _send_main

    await _send_main(cb.message, student)
    await cb.answer()


# ---------------------------------------------------------------- /cancel

@router.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext, student: dict | None):
    cur = await state.get_state()
    if student is None:
        await state.clear()
        await m.answer("❌ Отменено. Нажмите /start для входа.")
        return
    if cur and cur.startswith("OnbSG"):
        data = await state.get_data()
        db.update_settings(
            student["id"],
            next_pair=data.get("next_pair", 1),
            next_pair_min=data.get("next_pair_min", 30),
            tomorrow=data.get("tomorrow", 1),
            tomorrow_time=data.get("tomorrow_time", "19:00"),
            misc=data.get("misc", 1),
        )
    await state.clear()
    await m.answer("❌ Ввод отменён.")
    await send_main(m, student)
