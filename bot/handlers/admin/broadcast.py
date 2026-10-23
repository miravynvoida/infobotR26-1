"""Уведомление всем (рассылка)."""
import asyncio

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ... import db
from ...states import BcSG

router = Router()


@router.callback_query(F.data == "adm:bc")
async def bc_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(BcSG.text)
    await cb.answer()
    try:
        await cb.message.edit_text(
            "📣 <b>Уведомление всем</b>\n\nВведите текст, который получат все авторизованные студенты:\n"
            "<i>/cancel — отмена</i>"
        )
    except TelegramBadRequest:
        pass


@router.message(BcSG.text, F.text & ~F.text.startswith("/"))
async def bc_text(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await state.set_state(BcSG.confirm)
    await m.answer(
        f"👀 <b>Предпросмотр</b>\n\n{m.text}\n\nОтправить?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Отправить всем", callback_data="adm:bc:go")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="hwd:cancel")],
            ]
        ),
    )


@router.callback_query(BcSG.confirm, F.data == "adm:bc:go")
async def bc_go(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("text") or ""
    await state.clear()
    await cb.answer("Отправляю…")
    sent = 0
    total = 0
    for st in db.authorized_students():
        total += 1
        try:
            await cb.bot.send_message(st["tg_id"], text)
            sent += 1
        except TelegramAPIError:
            continue
        await asyncio.sleep(0.05)
    try:
        await cb.message.edit_text(f"📣 Отправлено: <b>{sent}</b> из {total} студентов.")
    except TelegramBadRequest:
        pass
