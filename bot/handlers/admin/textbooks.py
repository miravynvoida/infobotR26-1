"""Управление учебниками (админ)."""
import json

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ... import db
from ...keyboards import _grid
from ...services import schedule_utils as su
from ...states import TbEdSG, TbNewSG
from .homework import file_desc_from_message, files_manage_kb, files_wait_kb

router = Router()


def tb_admin_kb() -> InlineKeyboardMarkup:
    with_tb = {t["discipline_id"] for t in db.all_textbooks()}
    items = [
        (f"{'✅' if d['id'] in with_tb else '⬜'} {d['emoji']} {d['name']}", f"adm:tbd:{d['id']}")
        for d in db.all_disciplines()
    ]
    rows = _grid(items, 2)
    rows.append([InlineKeyboardButton(text="◀ Админ-панель", callback_data="adm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tb_list_kb(disc_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t["title"], callback_data=f"adm:tbi:{t['id']}")]
        for t in db.textbooks_by_discipline(disc_id)
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить учебник", callback_data=f"adm:tb:new:{disc_id}")])
    rows.append([InlineKeyboardButton(text="◀ К дисциплинам", callback_data="adm:tb")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tb_html(t: dict) -> str:
    files = json.loads(t.get("files") or "[]")
    lines = [f"📖 {t['emoji']} <b>{su.esc(t['discipline'])}</b>", "", f"🏷 <b>{su.esc(t['title'])}</b>"]
    if t.get("description"):
        lines.append(f"📝 {su.esc(t['description'])}")
    lines.append(f"📎 Файлов: {len(files)}")
    return "\n".join(lines)


def tb_item_kb(t: dict) -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="✏️ Название", callback_data=f"adm:tb:f:{t['id']}:title"),
             B(text="📝 Описание", callback_data=f"adm:tb:f:{t['id']}:desc")],
            [B(text="📎 Файлы", callback_data=f"adm:tb:fl:{t['id']}"),
             B(text="🗑 Удалить", callback_data=f"adm:tb:delc:{t['id']}")],
            [B(text="◀ К списку", callback_data=f"adm:tbd:{t['discipline_id']}")],
        ]
    )


@router.callback_query(F.data == "adm:tb")
async def tb_admin_menu(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text(
            "📖 <b>Управление учебниками</b>\n✅ есть учебники • ⬜ пусто", reply_markup=tb_admin_kb()
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp_match(r"^adm:tbd:\d+$"))
async def tb_disc_items(cb: CallbackQuery):
    disc_id = int(cb.data.split(":")[2])
    await cb.answer()
    try:
        await cb.message.edit_text("📖 Учебники дисциплины:", reply_markup=tb_list_kb(disc_id))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp_match(r"^adm:tbi:\d+$"))
async def tb_item(cb: CallbackQuery):
    t = db.textbook_by_id(int(cb.data.split(":")[2]))
    if t is None:
        await cb.answer("Не найден", show_alert=True)
        return
    await cb.answer()
    try:
        await cb.message.edit_text(tb_html(t), reply_markup=tb_item_kb(t))
    except TelegramBadRequest:
        pass


# ------------------------------------------------------------------ добавить

@router.callback_query(F.data.regexp_match(r"^adm:tb:new:\d+$"))
async def tb_new_start(cb: CallbackQuery, state: FSMContext):
    disc_id = int(cb.data.split(":")[3])
    await state.set_state(TbNewSG.title)
    await state.update_data(disc_id=disc_id, files=[])
    await cb.answer()
    await cb.message.edit_text("➕ 1/3 Введите название учебника/материала:")


@router.message(TbNewSG.title, F.text & ~F.text.startswith("/"))
async def tb_new_title(m: Message, state: FSMContext):
    await state.update_data(title=(m.text or "").strip())
    await state.set_state(TbNewSG.desc)
    await m.answer("2/3 Введите описание или «-»:")


@router.message(TbNewSG.desc, F.text)
async def tb_new_desc(m: Message, state: FSMContext):
    text = (m.text or "").strip()
    await state.update_data(desc=None if text in ("-", "—") else text)
    await state.set_state(TbNewSG.files)
    msg = await m.answer(
        "3/3 📎 Прикрепите файлы по одному сообщению или «✅ Без файлов»:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Без файлов", callback_data="atb:nof")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="hwd:cancel")],
            ]
        ),
    )
    await state.update_data(fmsg=msg.message_id)


@router.message(TbNewSG.files, F.document | F.photo | F.video | F.audio | F.animation | F.voice | F.video_note)
async def tb_new_file(m: Message, state: FSMContext):
    desc = file_desc_from_message(m)
    if desc is None:
        return
    data = await state.get_data()
    files = data.get("files") or []
    files.append(desc)
    if data.get("fmsg"):
        try:
            await m.bot.delete_message(m.chat.id, data["fmsg"])
        except TelegramAPIError:
            pass
    msg = await m.answer(
        f"📎 Файл «{su.esc(desc['name'])}» добавлен. Всего: <b>{len(files)}</b>.",
        reply_markup=files_wait_kb("atb:done"),
    )
    await state.update_data(files=files, fmsg=msg.message_id)


@router.callback_query(TbNewSG.files, F.data == "atb:nof")
async def tb_new_finish_none(cb: CallbackQuery, state: FSMContext):
    await state.update_data(files=[])
    await tb_new_finish(cb, state)


@router.callback_query(F.data == "atb:done")
async def tb_new_finish(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("fmsg"):
        try:
            await cb.bot.delete_message(cb.message.chat.id, data["fmsg"])
        except TelegramAPIError:
            pass
    tid = db.create_textbook(data["disc_id"], data.get("title") or "—", data.get("desc"), data.get("files") or [])
    await state.clear()
    t = db.textbook_by_id(tid)
    await cb.answer()
    await cb.message.edit_text("✅ Учебник добавлен.\n\n" + tb_html(t), reply_markup=tb_item_kb(t))


# ------------------------------------------------------------------ редактировать

@router.callback_query(F.data.regexp_match(r"^adm:tb:f:\d+:(title|desc)$"))
async def tb_edit_field(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    tid, field = int(parts[3]), parts[4]
    await state.set_state(TbEdSG.input)
    await state.update_data(tid=tid, field=field)
    await cb.answer()
    await cb.message.edit_text("✏️ Введите новое название:" if field == "title" else "✏️ Введите описание (или «-»):")


@router.message(TbEdSG.input, F.text & ~F.text.startswith("/"))
async def tb_edit_input(m: Message, state: FSMContext):
    data = await state.get_data()
    t = db.textbook_by_id(data["tid"])
    if t is None:
        await state.clear()
        await m.answer("⚠️ Не найден.")
        return
    text = (m.text or "").strip()
    if data["field"] == "title":
        db.update_textbook(t["id"], title=text)
    else:
        db.update_textbook(t["id"], description=None if text in ("-", "—") else text)
    await state.clear()
    t = db.textbook_by_id(t["id"])
    await m.answer("✅ Сохранено.")
    await m.answer(tb_html(t), reply_markup=tb_item_kb(t))


@router.callback_query(F.data.regexp_match(r"^adm:tb:fl:\d+$"))
async def tb_files_menu(cb: CallbackQuery, state: FSMContext):
    tid = int(cb.data.split(":")[3])
    t = db.textbook_by_id(tid)
    if t is None:
        await cb.answer("Не найден", show_alert=True)
        return
    files = json.loads(t.get("files") or "[]")
    await state.set_state(TbEdSG.files)
    await state.update_data(tid=tid, files=files, fdel=[])
    await cb.answer()
    await cb.message.edit_text(
        "📎 Управление файлами (нажмите, чтобы пометить на удаление):",
        reply_markup=files_manage_kb(files, set(), f"atbd", f"atbfa:{tid}", f"atbfw:{tid}", f"adm:tbi:{tid}"),
    )


@router.callback_query(TbEdSG.files, F.data.regexp_match(r"^atbd:\d+$"))
async def tb_file_toggle(cb: CallbackQuery, state: FSMContext):
    i = int(cb.data.split(":")[1])
    data = await state.get_data()
    files = data.get("files") or []
    marked = set(data.get("fdel") or [])
    if i >= len(files):
        await cb.answer()
        return
    marked.symmetric_difference_update({i})
    await state.update_data(fdel=sorted(marked))
    await cb.answer("🗑 Помечено" if i in marked else "↩️ Оставить")
    try:
        await cb.message.edit_text(
            "📎 Управление файлами:",
            reply_markup=files_manage_kb(files, marked, "atbd", f"atbfa:{data['tid']}", f"atbfw:{data['tid']}", f"adm:tbi:{data['tid']}"),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp_match(r"^atbfa:\d+$"))
async def tb_files_add(cb: CallbackQuery, state: FSMContext):
    tid = int(cb.data.split(":")[2])
    await state.set_state(TbEdSG.files)
    await cb.answer()
    msg = await cb.message.edit_text(
        "➕ Прикрепите файлы сообщениями, затем «✅ Готово»:", reply_markup=files_wait_kb("atbfw")
    )
    await state.update_data(fmsg=msg.message_id if hasattr(msg, "message_id") else None)


@router.message(TbEdSG.files, F.document | F.photo | F.video | F.audio | F.animation | F.voice | F.video_note)
async def tb_files_attach(m: Message, state: FSMContext):
    desc = file_desc_from_message(m)
    if desc is None:
        return
    data = await state.get_data()
    files = data.get("files") or []
    files.append(desc)
    if data.get("fmsg"):
        try:
            await m.bot.delete_message(m.chat.id, data["fmsg"])
        except TelegramAPIError:
            pass
    msg = await m.answer(
        f"📎 Файл «{su.esc(desc['name'])}» добавлен. Всего: <b>{len(files)}</b>.",
        reply_markup=files_wait_kb("atbfw"),
    )
    await state.update_data(files=files, fmsg=msg.message_id)


@router.callback_query(F.data.regexp_match(r"^atbfw:\d+$"))
async def tb_files_apply(cb: CallbackQuery, state: FSMContext):
    tid = int(cb.data.split(":")[2])
    data = await state.get_data()
    if data.get("fmsg"):
        try:
            await cb.bot.delete_message(cb.message.chat.id, data["fmsg"])
        except TelegramAPIError:
            pass
    files = data.get("files") or []
    marked = set(data.get("fdel") or [])
    files = [f for i, f in enumerate(files) if i not in marked]
    db.update_textbook(tid, files=files)
    t = db.textbook_by_id(tid)
    await state.clear()
    await cb.answer("Файлы обновлены")
    await cb.message.edit_text(tb_html(t), reply_markup=tb_item_kb(t))


# ------------------------------------------------------------------ удалить

@router.callback_query(F.data.regexp_match(r"^adm:tb:delc:\d+$"))
async def tb_del_confirm(cb: CallbackQuery):
    tid = int(cb.data.split(":")[3])
    await cb.answer()
    await cb.message.edit_text(
        "🗑 Удалить учебник?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"adm:tb:del:{tid}")],
                [InlineKeyboardButton(text="◀ Отмена", callback_data=f"adm:tbi:{tid}")],
            ]
        ),
    )


@router.callback_query(F.data.regexp_match(r"^adm:tb:del:\d+$"))
async def tb_delete(cb: CallbackQuery):
    tid = int(cb.data.split(":")[3])
    db.delete_textbook(tid)
    await cb.answer("Удалён")
    await cb.message.edit_text("📖 <b>Управление учебниками</b>", reply_markup=tb_admin_kb())
