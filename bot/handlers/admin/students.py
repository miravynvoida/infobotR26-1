"""Управление студентами."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ... import db
from ...services import schedule_utils as su
from ...states import StudNewSG

router = Router()


def students_kb() -> InlineKeyboardMarkup:
    rows = []
    for st in db.all_students():
        mark = "🟢" if st["tg_id"] else "⚪"
        rows.append([InlineKeyboardButton(text=f"{mark} {st['fio']}", callback_data=f"adm:stu:{st['id']}")])
    rows.append([InlineKeyboardButton(text="➕ Добавить студента", callback_data="adm:stu:add")])
    rows.append([InlineKeyboardButton(text="◀ Админ-панель", callback_data="adm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def student_kb(st: dict) -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    if st["tg_id"]:
        unlink = B(text="🔓 Отвязать TG", callback_data=f"adm:stu:unl:{st['id']}")
    else:
        unlink = B(text="⚪ Не авторизован", callback_data="noop")
    muted = db.is_muted(st["id"])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="🔄 Новый код", callback_data=f"adm:stu:code:{st['id']}"), unlink],
            [
                B(
                    text="🔕 Уведомления: включить" if muted else "🔔 Отключить все уведомления",
                    callback_data=f"adm:stu:{'unmut' if muted else 'mut'}:{st['id']}",
                )
            ],
            [B(text="🗑 Удалить", callback_data=f"adm:stu:delc:{st['id']}")],
            [B(text="◀ К списку", callback_data="adm:studs")],
        ]
    )


def student_html(st: dict) -> str:
    if st["tg_id"]:
        status = f"🟢 Авторизован (TG ID: <code>{st['tg_id']}</code>"
        if st.get("authorized_at"):
            a = st["authorized_at"]
            status += f", с {a[8:10]}.{a[5:7]}.{a[:4]}"
        status += ")"
    else:
        status = "⚪ Не авторизован"
    muted = db.is_muted(st["id"])
    mute_line = (
        "🔕 <b>Все уведомления отключены администратором</b>"
        if muted
        else "🔔 Уведомления включены"
    )
    return (
        f"👤 <b>{su.esc(st['fio'])}</b>\n\n"
        f"{status}\n"
        f"🔑 Код входа: <code>{st['code']}</code>\n"
        f"{mute_line}"
    )


@router.callback_query(F.data == "adm:studs")
async def students_list(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text(
            "👥 <b>Студенты</b>\n🟢 авторизован • ⚪ не авторизован",
            reply_markup=students_kb(),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "adm:stu:add")
async def student_add_prompt(cb: CallbackQuery, state: FSMContext):
    await state.set_state(StudNewSG.fio)
    await cb.answer()
    try:
        await cb.message.edit_text("➕ Введите ФИО нового студента:\n<i>/cancel — отмена</i>")
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("adm:stu:"))
async def student_actions(cb: CallbackQuery, state: FSMContext):
    # форматы: adm:stu:{id} (просмотр) и adm:stu:{action}:{id}
    parts = cb.data.split(":")
    if len(parts) == 3 and parts[2].isdigit():
        action, sid = "view", int(parts[2])
    else:
        action, sid = parts[2], int(parts[3])
    st = db.student_by_id(sid)
    if st is None:
        await cb.answer("Не найден", show_alert=True)
        return

    if action == "view":
        await cb.answer()
        await cb.message.edit_text(student_html(st), reply_markup=student_kb(st))
    elif action == "code":
        code = db.regen_code(st["id"])
        st = db.student_by_id(st["id"])
        await cb.answer(f"Новый код: {code}", show_alert=True)
        await cb.message.edit_text(student_html(st), reply_markup=student_kb(st))
    elif action == "unl":
        db.unlink_tg(st["id"])
        st = db.student_by_id(st["id"])
        await cb.answer("Привязка сброшена")
        await cb.message.edit_text(
            student_html(st) + "\n\n🔓 Привязка к Telegram сброшена.", reply_markup=student_kb(st)
        )
    elif action in ("mut", "unmut"):
        db.set_mute(st["id"], action == "mut")
        await cb.answer("🔕 Уведомления отключены" if action == "mut" else "🔔 Уведомления включены")
        try:
            await cb.message.edit_text(student_html(st), reply_markup=student_kb(st))
        except TelegramBadRequest:
            pass
    elif action == "delc":
        await cb.answer()
        await cb.message.edit_text(
            f"🗑 Удалить <b>{su.esc(st['fio'])}</b>? Вместе с оценками и посещаемостью. Действие необратимо.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"adm:stu:del:{st['id']}")],
                    [InlineKeyboardButton(text="◀ Отмена", callback_data=f"adm:stu:view:{st['id']}")],
                ]
            ),
        )
    elif action == "del":
        db.delete_student(st["id"])
        await cb.answer("Удалён")
        await cb.message.edit_text("👥 <b>Студенты</b>", reply_markup=students_kb())


@router.message(StudNewSG.fio, F.text & ~F.text.startswith("/"))
async def student_add(m: Message, state: FSMContext):
    fio = " ".join((m.text or "").split())
    if not fio:
        await m.answer("⚠️ Введите ФИО:")
        return
    if db.student_by_fio(fio):
        await m.answer("⚠️ Такой студент уже есть. Введите другое ФИО:")
        return
    st = db.add_student(fio)
    await state.clear()
    await m.answer(
        f"✅ Добавлен: <b>{su.esc(st['fio'])}</b>\n🔑 Код входа: <code>{st['code']}</code>",
        reply_markup=students_kb(),
    )
