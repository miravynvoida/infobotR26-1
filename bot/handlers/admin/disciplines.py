"""Управление дисциплинами."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ... import db
from ...keyboards import _grid
from ...services import schedule_utils as su
from ...states import DiscEdSG, DiscNewSG

router = Router()


def disciplines_kb() -> InlineKeyboardMarkup:
    items = [(f"{d['emoji']} {d['name']}", f"adm:di:{d['id']}") for d in db.all_disciplines()]
    rows = _grid(items, 2)
    rows.append([InlineKeyboardButton(text="➕ Добавить дисциплину", callback_data="adm:di:add")])
    rows.append([InlineKeyboardButton(text="◀ Админ-панель", callback_data="adm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def discipline_kb(d: dict) -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="✏️ Название", callback_data=f"adm:di:f:{d['id']}:name"),
             B(text="😀 Эмодзи", callback_data=f"adm:di:f:{d['id']}:emoji")],
            [B(text="👩‍🏫 Преподаватель", callback_data=f"adm:di:f:{d['id']}:teacher"),
             B(text="🗑 Удалить", callback_data=f"adm:di:delc:{d['id']}")],
            [B(text="◀ К списку", callback_data="adm:disc")],
        ]
    )


def discipline_html(d: dict) -> str:
    usage = db.discipline_usage(d["id"])
    return (
        f"📐 {d['emoji']} <b>{su.esc(d['name'])}</b>\n"
        f"👩‍🏫 {su.esc(d['teacher'] or '—')}\n\n"
        f"Использование: расписание {usage['schedule']} • ДЗ {usage['homework']} • "
        f"учебники {usage['textbooks']} • оценки {usage['grades']}"
    )


@router.callback_query(F.data == "adm:disc")
async def disciplines_list(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text("📐 <b>Дисциплины</b>", reply_markup=disciplines_kb())
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "adm:di:add")
async def disc_add(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(DiscNewSG.name)
    try:
        await cb.message.edit_text("➕ Введите название дисциплины:\n<i>/cancel — отмена</i>")
    except TelegramBadRequest:
        pass


@router.message(DiscNewSG.name, F.text & ~F.text.startswith("/"))
async def disc_add_name(m: Message, state: FSMContext):
    name = (m.text or "").strip()
    if db.discipline_by_name(name):
        await m.answer("⚠️ Такая дисциплина уже есть. Введите другое название:")
        return
    await state.update_data(name=name)
    await state.set_state(DiscNewSG.emoji)
    await m.answer("😀 Введите эмодзи дисциплины или «-» для стандартного (📚):")


@router.message(DiscNewSG.emoji, F.text)
async def disc_add_emoji(m: Message, state: FSMContext):
    emoji = (m.text or "").strip()
    await state.update_data(emoji=None if emoji == "-" else emoji[:4])
    await state.set_state(DiscNewSG.teacher)
    await m.answer("👩‍🏫 Введите преподавателя (Фамилия И.О.) или «-»:")


@router.message(DiscNewSG.teacher, F.text)
async def disc_add_teacher(m: Message, state: FSMContext):
    teacher = (m.text or "").strip()
    data = await state.get_data()
    db.ensure_discipline(data["name"], data.get("emoji") or "📚", None if teacher == "-" else teacher)
    await state.clear()
    await m.answer("✅ Дисциплина добавлена.", reply_markup=disciplines_kb())


@router.callback_query(F.data.startswith("adm:di:f:"))
async def disc_edit_field(cb: CallbackQuery, state: FSMContext):
    # adm:di:f:{id}:{field}
    parts = cb.data.split(":")
    did, field = int(parts[3]), parts[4]
    d = db.discipline_by_id(did)
    if d is None:
        await cb.answer("Не найдена", show_alert=True)
        return
    await state.set_state(DiscEdSG.input)
    await state.update_data(did=did, field=field)
    prompts = {
        "name": "✏️ Введите новое название дисциплины:",
        "emoji": "😀 Введите новый эмодзи:",
        "teacher": "👩‍🏫 Введите преподавателя (или «-» чтобы убрать):",
    }
    await cb.answer()
    try:
        await cb.message.edit_text(prompts[field])
    except TelegramBadRequest:
        pass


@router.message(DiscEdSG.input, F.text & ~F.text.startswith("/"))
async def disc_edit_input(m: Message, state: FSMContext):
    data = await state.get_data()
    d = db.discipline_by_id(data["did"])
    if d is None:
        await state.clear()
        await m.answer("⚠️ Дисциплина не найдена.")
        return
    value = (m.text or "").strip()
    field = data["field"]
    if field == "name":
        db.ex("UPDATE disciplines SET name=?, name_norm=? WHERE id=?", (value, db.norm_name(value), d["id"]))
    elif field == "emoji":
        db.ex("UPDATE disciplines SET emoji=? WHERE id=?", (value[:4] or "📚", d["id"]))
    elif field == "teacher":
        db.ex("UPDATE disciplines SET teacher=? WHERE id=?", (None if value == "-" else value, d["id"]))
    await state.clear()
    d = db.discipline_by_id(d["id"])
    await m.answer("✅ Сохранено.", reply_markup=None)
    await m.answer(discipline_html(d), reply_markup=discipline_kb(d))


@router.callback_query(F.data.startswith("adm:di:delc:"))
async def disc_del_confirm(cb: CallbackQuery):
    did = int(cb.data.split(":")[3])
    d = db.discipline_by_id(did)
    if d is None:
        await cb.answer("Не найдена", show_alert=True)
        return
    usage = db.discipline_usage(did)
    total = sum(usage.values())
    await cb.answer()
    if total:
        await cb.message.edit_text(
            discipline_html(d)
            + "\n\n⚠️ Нельзя удалить: дисциплина используется (см. использование выше).",
            reply_markup=discipline_kb(d),
        )
        return
    await cb.message.edit_text(
        f"🗑 Удалить дисциплину <b>{su.esc(d['name'])}</b>?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"adm:di:del:{did}")],
                [InlineKeyboardButton(text="◀ Отмена", callback_data=f"adm:di:{did}")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adm:di:del:"))
async def disc_delete(cb: CallbackQuery):
    did = int(cb.data.split(":")[3])
    db.ex("DELETE FROM disciplines WHERE id=?", (did,))
    await cb.answer("Удалена")
    await cb.message.edit_text("📐 <b>Дисциплины</b>", reply_markup=disciplines_kb())


@router.callback_query(F.data.regexp_match(r"^adm:di:\d+$"))
async def disc_view(cb: CallbackQuery):
    did = int(cb.data.split(":")[2])
    d = db.discipline_by_id(did)
    if d is None:
        await cb.answer("Не найдена", show_alert=True)
        return
    await cb.answer()
    try:
        await cb.message.edit_text(discipline_html(d), reply_markup=discipline_kb(d))
    except TelegramBadRequest:
        pass
