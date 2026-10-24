"""Авторизационная middleware и фильтр админа.

Middleware только обогащает data (student/is_admin/is_staff) и блокирует
inline-кнопки для неавторизованных (у них всё равно нет клавиатур бота).
Обычные сообщения не блокируются: лишние ловит финальный fallback в menu.py
и просит нажать /start — вход по ФИО и коду работает при любых раскладах.
"""
from aiogram import BaseMiddleware
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from . import config, db
from .services import maintenance as mnt


class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user is not None and not user.is_bot:
            student = db.student_by_tg(user.id)
            data["student"] = student
            data["is_admin"] = user.id in config.cfg.admin_ids
            data["is_staff"] = user.id in config.cfg.staff_ids
            if student is None and isinstance(event, CallbackQuery):
                await event.answer("⛔ Нет доступа. Войдите через /start", show_alert=True)
                return
            st = mnt.maintenance_state()
            if st["on"] and user.id not in config.cfg.admin_ids:
                text = mnt.maintenance_text()
                if isinstance(event, Message):
                    await event.answer(text)
                else:
                    await event.answer("🛠 Тех. работы — бот временно недоступен", show_alert=True)
                return
        return await handler(event, data)


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, is_admin: bool = False) -> bool:
        return bool(is_admin)
