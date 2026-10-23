"""Корень админ-панели."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

router = Router()


def admin_panel_kb() -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="📚 ДЗ", callback_data="adm:hw"), B(text="📅 Расписание", callback_data="adm:sch")],
            [B(text="📖 Учебники", callback_data="adm:tb"), B(text="📊 Обзор и статистика", callback_data="adm:st")],
            [B(text="👥 Студенты", callback_data="adm:studs"), B(text="📐 Дисциплины", callback_data="adm:disc")],
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
