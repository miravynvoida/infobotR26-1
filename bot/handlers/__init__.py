"""Сборка диспетчера из всех роутеров."""
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from ..middlewares import AuthMiddleware
from .admin import build_admin_router


def build_dispatcher() -> Dispatcher:
    from . import attendance, auth, cabinet, homework, menu, schedule, textbooks

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(AuthMiddleware())
    dp.callback_query.outer_middleware(AuthMiddleware())

    dp.include_router(auth.router)
    dp.include_router(build_admin_router())
    dp.include_router(schedule.router)
    dp.include_router(homework.router)
    dp.include_router(textbooks.router)
    dp.include_router(cabinet.router)
    dp.include_router(attendance.router)
    dp.include_router(menu.router)  # последний: ловит всё остальное
    return dp
