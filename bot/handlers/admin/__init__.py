"""Админ-панель: сборка роутера."""
from aiogram import Router

from ...middlewares import IsAdmin
from . import broadcast, disciplines, homework, panel, schedule, statistics, students, textbooks


def build_admin_router() -> Router:
    router = Router(name="admin")
    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())
    router.include_router(panel.router)
    router.include_router(homework.router)
    router.include_router(schedule.router)
    router.include_router(students.router)
    router.include_router(disciplines.router)
    router.include_router(textbooks.router)
    router.include_router(statistics.router)
    router.include_router(broadcast.router)
    return router
