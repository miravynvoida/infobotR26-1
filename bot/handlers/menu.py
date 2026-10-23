"""Главное меню, /help, /id, ловушки необработанных апдейтов."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import config, db
from ..keyboards import main_menu
from ..services import schedule_utils as su
from ..states import AuthSG

router = Router()


def main_menu_html() -> str:
    return (
        f"👋 <b>Добро пожаловать в информационного бота {su.esc(config.cfg.group_name)}!</b>\n\n"
        "Здесь можно посмотреть расписание, домашние задания, учебники и оценки.\n\n"
        f"{su.main_status_html()}"
    )


async def send_main(target: Message, student: dict, is_admin: bool = False) -> None:
    """target — сообщение для ответа. Кнопку админа добавляем по tg_id."""
    is_admin = is_admin or target.from_user.id in config.cfg.admin_ids
    await target.answer(main_menu_html(), reply_markup=main_menu(is_admin))


async def edit_main(cb: CallbackQuery, is_admin: bool) -> None:
    try:
        await cb.message.edit_text(main_menu_html(), reply_markup=main_menu(is_admin))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "home")
async def go_home(cb: CallbackQuery, state: FSMContext, is_admin: bool):
    await state.clear()
    await cb.answer()
    if cb.message:
        await edit_main(cb, is_admin)


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


@router.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer(
        "❓ <b>Справка</b>\n\n"
        "• 📅 Расписание — сегодня, завтра, любой день месяца\n"
        "• 📚 ДЗ — задания по дисциплинам, отметка «выполнено»\n"
        "• 📖 Учебники — материалы по предметам\n"
        "• 👤 Кабинет — оценки, пропуски, настройки уведомлений\n"
        "• 🖥 Приложение — дневник с оценками и расписанием\n\n"
        "Утром бот спрашивает, будете ли вы на парах — на него нужно ответить, "
        "сводка уходит старосте и заму.\n\n"
        "/cancel — отменить незавершённый ввод.\n"
        f"Вопросы: {su.esc(config.cfg.support_url)}"
    )


@router.message(Command("id"))
async def cmd_id(m: Message, student: dict | None):
    """Доступна всем (даже неавторизованным) — показывает TG ID и версию сборки."""
    lines = [
        f"🆔 Ваш TG ID: <code>{m.from_user.id}</code>",
        f"Сборка бота: <b>{config.BUILD_TAG}</b>",
        f"Студентов в базе: {len(db.all_students())}",
    ]
    if student:
        lines.append(f"Вы авторизованы как: {su.esc(student['fio'])}")
    else:
        lines.append("Статус: не авторизованы — войдите через /start")
    await m.answer("\n".join(lines))


@router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def fallback_text(m: Message, state: FSMContext, student: dict | None, is_admin: bool):
    if student is None:
        # Подстраховка: если состояние входа потерялось (перезапуск контейнера),
        # всё равно распознаём ФИО и продолжаем авторизацию с шага ввода кода.
        fio = " ".join((m.text or "").split())
        st = db.student_by_fio(fio) if fio else None
        if st and st["tg_id"] is None:
            await state.update_data(sid=st["id"])
            await state.set_state(AuthSG.code)
            await m.answer(
                f"✅ Найдено: <b>{su.esc(st['fio'])}</b>\n\n"
                "Теперь введите <b>индивидуальный код входа</b> "
                "(смотрите в логах запуска бота или получите у старосты/зама)."
            )
            return
        if st and st["tg_id"]:
            await m.answer(
                "⛔ Этот студент уже авторизован с другого аккаунта. "
                "Обратитесь к старосте или заму — они сбросят привязку (Админка → Студенты)."
            )
            return
        await m.answer("⛔ Доступ только для студентов группы. Войдите через /start.")
        return
    await send_main(m, student, is_admin)


@router.message(StateFilter(None))
async def fallback_any(m: Message, student: dict | None, is_admin: bool):
    if student is None:
        await m.answer("⛔ Доступ только для студентов группы. Войдите через /start.")
        return
    await send_main(m, student, is_admin)


@router.callback_query()
async def fallback_cb(cb: CallbackQuery):
    await cb.answer("Кнопка недоступна. /cancel — сброс.", show_alert=False)
