"""Управление домашним заданием (админ).

Фильтры — только точные и префиксные (без regexp_match): одинаково работает
на любой версии aiogram. Порядок: точные → специфичные префиксы → generic.
"""
import json

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ... import db
from ...keyboards import _grid
from ...services import schedule_utils as su
from ...services.tg_files import hw_notice_html
from ...states import HwNewSG

router = Router()


def _int(s: str) -> int | None:
    return int(s) if s.isdigit() else None


# ------------------------------------------------------------------ клавиатуры

def hw_admin_kb() -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="➕ Новое ДЗ", callback_data="adm:hw:new"), B(text="📋 Существующие", callback_data="adm:hw:l")],
            [B(text="📦 Архив", callback_data="adm:hw:arc")],
            [B(text="◀ Админ-панель", callback_data="adm")],
        ]
    )


def hw_discs_kb(archived: int) -> InlineKeyboardMarkup:
    rows_data = db.homework_by_discipline(archived)
    seen: dict[int, str] = {}
    for h in rows_data:
        seen.setdefault(h["discipline_id"], f"{h['emoji']} {h['discipline']}")
    items = [(name, f"adm:hw:d:{did}") for did, name in seen.items()]
    rows = _grid(items, 2)
    rows.append([InlineKeyboardButton(text="◀ К меню ДЗ", callback_data="adm:hw")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def hw_items_kb(disc_id: int, archived: int) -> InlineKeyboardMarkup:
    rows = []
    for h in db.homework_by_discipline(archived):
        if h["discipline_id"] != disc_id:
            continue
        due = su.fmt_dm(h["due_date"]) if h.get("due_date") else "—"
        n_files = len(json.loads(h.get("files") or "[]"))
        label = f"{due} • {h['title']} 📎{n_files}" if n_files else f"{due} • {h['title']}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"adm:hw:i:{h['id']}")])
    rows.append(
        [InlineKeyboardButton(text="◀ К дисциплинам", callback_data=f"adm:hw:{'arc' if archived else 'l'}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def hw_item_kb(h: dict) -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    back = "adm:hw:arc" if h["archived"] else f"adm:hw:d:{h['discipline_id']}"
    rows = []
    if not h["archived"]:
        rows.append([B(text="✏️ Редактировать", callback_data=f"adm:hw:e:{h['id']}")])
        rows.append([B(text="📦 В архив", callback_data=f"adm:hw:arc2:{h['id']}"),
                     B(text="🗑 Удалить", callback_data=f"adm:hw:delc:{h['id']}")])
    else:
        rows.append([B(text="♻️ Восстановить", callback_data=f"adm:hw:res:{h['id']}"),
                     B(text="🗑 Удалить", callback_data=f"adm:hw:delc:{h['id']}")])
    rows.append([B(text="◀ Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def hw_edit_fields_kb(hid: int) -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="🏷 Название", callback_data=f"adm:hw:f:{hid}:title"),
             B(text="📝 Задание", callback_data=f"adm:hw:f:{hid}:task")],
            [B(text="📅 Срок сдачи", callback_data=f"adm:hw:f:{hid}:due"),
             B(text="🕐 Дата публикации", callback_data=f"adm:hw:f:{hid}:pub")],
            [B(text="💡 Пояснение", callback_data=f"adm:hw:f:{hid}:expl"),
             B(text="📐 Дисциплина", callback_data=f"adm:hw:f:{hid}:disc")],
            [B(text="📎 Файлы", callback_data=f"adm:hw:f:{hid}:files")],
            [B(text="◀ К заданию", callback_data=f"adm:hw:i:{hid}")],
        ]
    )


def due_options_kb(options: list[dict], cb_sel: str, cb_custom: str) -> InlineKeyboardMarkup:
    rows = []
    for i, o in enumerate(options):
        label = f"{o['type'] or 'Пара'} • {su.wd_lower(o['date'])} {su.fmt_dm(o['date'])}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"{cb_sel}:{i}")])
    rows.append([InlineKeyboardButton(text="📆 Своя дата (DD.MM.YYYY)", callback_data=cb_custom)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def files_manage_kb(files, marked, cb_del, cb_add, cb_ok, cb_back) -> InlineKeyboardMarkup:
    rows = []
    for i, f in enumerate(files):
        mark = "✅ " if i in marked else "🗑 "
        rows.append([InlineKeyboardButton(text=f"{mark}{f.get('name') or 'файл'}", callback_data=f"{cb_del}:{i}")])
    rows.append([InlineKeyboardButton(text="➕ Добавить файлы", callback_data=cb_add)])
    rows.append([InlineKeyboardButton(text="✅ Готово", callback_data=cb_ok)])
    rows.append([InlineKeyboardButton(text="◀ Отмена", callback_data=cb_back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def files_wait_kb(done_cb: str = "hwd:fok") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data=done_cb)],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="hwd:cancel")],
        ]
    )


def preview_kb() -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="✅ Опубликовать", callback_data="hwd:pub")],
            [B(text="🔄 Заполнить заново", callback_data="hwd:rf")],
            [B(text="❌ Отмена", callback_data="hwd:cancel")],
        ]
    )


def refill_kb() -> InlineKeyboardMarkup:
    B = InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [B(text="🏷 Название", callback_data="hwd:rf:title"), B(text="📝 Задание", callback_data="hwd:rf:task")],
            [B(text="📅 Срок сдачи", callback_data="hwd:rf:due"), B(text="🕐 Дата публикации", callback_data="hwd:rf:pub")],
            [B(text="💡 Пояснение", callback_data="hwd:rf:expl"), B(text="📐 Дисциплина", callback_data="hwd:rf:disc")],
            [B(text="📎 Файлы", callback_data="hwd:rf:files")],
            [B(text="◀ К предпросмотру", callback_data="hwd:rf:back")],
        ]
    )


def disc_grid_kb(cb: str) -> InlineKeyboardMarkup:
    items = [(f"{d['emoji']} {d['name']}", f"{cb}:{d['id']}") for d in db.all_disciplines()]
    return InlineKeyboardMarkup(inline_keyboard=_grid(items, 2))


# ------------------------------------------------------------------ тексты

def hw_full_html(h: dict) -> str:
    files = json.loads(h.get("files") or "[]")
    lines = [
        f"📚 {h['emoji']} <b>{su.esc(h['discipline'])}</b>",
        "",
        f"🏷 <b>{su.esc(h['title'])}</b>",
        f"📝 Задание: {su.esc(h['task_text'])}",
    ]
    if h.get("due_date"):
        due = f"📅 Сдать до: {su.fmt_dmy(h['due_date'])} ({su.wd_lower(h['due_date'])})"
        if h.get("due_type"):
            due += f", к паре ({h['due_type']})"
        lines.append(due)
    pub = h.get("published_at") or ""
    if pub:
        lines.append(f"🕐 Публикация: {pub[8:10]}.{pub[5:7]}.{pub[:4]} {pub[11:16]}")
    if h.get("explanation"):
        lines.append(f"💡 Пояснение: {su.esc(h['explanation'])}")
    lines.append(f"📎 Файлов: {len(files)}")
    lines.append(f"Статус: {'📦 в архиве' if h['archived'] else '✅ активно'}")
    return "\n".join(lines)


def draft_preview_html(draft: dict) -> str:
    disc = db.discipline_by_id(draft["disc_id"])
    fake = {
        "discipline": disc["name"], "emoji": disc["emoji"], "title": draft.get("title"),
        "task_text": draft.get("task"), "due_date": draft.get("due"), "due_type": draft.get("due_type"),
        "published_at": draft.get("pub") or su.ts(), "explanation": draft.get("expl"),
        "files": json.dumps(draft.get("files") or [], ensure_ascii=False), "archived": 0,
    }
    return "👀 <b>Предпросмотр ДЗ</b>\n\n" + hw_full_html(fake)


async def show_preview(cb=None, state: FSMContext = None, edit_message: Message | None = None, bot=None, chat_id=None):
    data = await state.get_data()
    draft = data.get("draft") or {}
    draft["files"] = data.get("files") or draft.get("files") or []
    await state.update_data(draft=draft)
    await state.set_state(HwNewSG.preview)
    text = draft_preview_html(draft)
    if edit_message is not None:
        try:
            await edit_message.edit_text(text, reply_markup=preview_kb())
            return
        except TelegramBadRequest:
            pass
    if cb is not None and cb.message:
        try:
            await cb.message.edit_text(text, reply_markup=preview_kb())
            return
        except TelegramBadRequest:
            pass
    bot = bot or (cb.bot if cb else edit_message.bot)
    chat = chat_id or ((cb.message.chat.id if cb and cb.message else edit_message.chat.id) if edit_message or cb else None)
    await bot.send_message(chat, text, reply_markup=preview_kb())


async def edit_done(m: Message, state: FSMContext, hid: int):
    """Сохранили поле существующего ДЗ — показываем задание."""
    data = await state.get_data()
    draft = data.get("draft") or {}
    fields = {}
    if draft.get("title") is not None:
        fields["title"] = draft["title"]
    if draft.get("task") is not None:
        fields["task_text"] = draft["task"]
    if draft.get("due") is not None:
        fields["due_date"] = draft["due"]
        fields["due_type"] = draft.get("due_type")
    if draft.get("expl") is not None:
        fields["explanation"] = draft["expl"]
    if draft.get("pub") is not None:
        fields["published_at"] = draft["pub"]
    if draft.get("disc_id") is not None:
        fields["discipline_id"] = draft["disc_id"]
    if fields:
        db.update_hw(hid, **fields)
    h = db.hw_by_id(hid)
    await state.clear()
    await m.answer("✅ Сохранено.")
    await m.answer(hw_full_html(h), reply_markup=hw_item_kb(h))


def file_desc_from_message(m: Message) -> dict | None:
    if m.document:
        return {"type": "document", "name": m.document.file_name or "файл", "file_id": m.document.file_id}
    if m.photo:
        return {"type": "photo", "name": "фото", "file_id": m.photo[-1].file_id}
    if m.video:
        return {"type": "video", "name": m.video.file_name or "видео", "file_id": m.video.file_id}
    if m.audio:
        return {"type": "audio", "name": m.audio.file_name or "аудио", "file_id": m.audio.file_id}
    if m.animation:
        return {"type": "animation", "name": m.animation.file_name or "gif", "file_id": m.animation.file_id}
    if m.voice:
        return {"type": "voice", "name": "голосовое", "file_id": m.voice.file_id}
    if m.video_note:
        return {"type": "video_note", "name": "видеосообщение", "file_id": m.video_note.file_id}
    return None


# ------------------------------------------------------------------ меню ДЗ

@router.callback_query(F.data == "adm:hw")
async def hw_admin_menu(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text("📚 <b>Управление ДЗ</b>", reply_markup=hw_admin_kb())
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "adm:hw:new")
async def hw_new_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(HwNewSG.title)
    await state.update_data(draft=None, hw_id=None, field=None, mode="new", ok_cb="hwd:fok", files=[], fdel=[], fmsg=None)
    await cb.answer()
    await cb.message.edit_text("➕ <b>Новое ДЗ</b>\n\n1/6 Выберите дисциплину:", reply_markup=disc_grid_kb("hwd:disc"))


@router.callback_query(F.data == "adm:hw:l")
async def hw_list_discs(cb: CallbackQuery):
    if not db.homework_by_discipline(0):
        await cb.answer("Активных ДЗ нет", show_alert=True)
        return
    await cb.answer()
    try:
        await cb.message.edit_text("📋 <b>Существующие ДЗ</b> — дисциплины:", reply_markup=hw_discs_kb(0))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "adm:hw:arc")
async def hw_archive_list(cb: CallbackQuery):
    rows = db.archived_homework()
    if not rows:
        await cb.answer("Архив пуст", show_alert=True)
        return
    await cb.answer()
    kb_rows = [
        [InlineKeyboardButton(
            text=f"📦 {su.fmt_dm(h['due_date']) if h['due_date'] else '—'} • {h['emoji']} {h['title']}",
            callback_data=f"adm:hw:i:{h['id']}",
        )]
        for h in rows[:40]
    ]
    kb_rows.append([InlineKeyboardButton(text="◀ К меню ДЗ", callback_data="adm:hw")])
    try:
        await cb.message.edit_text("📦 <b>Архив ДЗ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("adm:hw:arc2:"))
async def hw_to_archive(cb: CallbackQuery):
    hid = _int(cb.data.split(":")[3])
    if hid is None:
        await cb.answer()
        return
    db.set_hw_archived(hid, True, su.ts())
    await cb.answer("📦 Перенесено в архив")
    h = db.hw_by_id(hid)
    await cb.message.edit_text(hw_full_html(h), reply_markup=hw_item_kb(h))


@router.callback_query(F.data.startswith("adm:hw:res:"))
async def hw_restore(cb: CallbackQuery):
    hid = _int(cb.data.split(":")[3])
    if hid is None:
        await cb.answer()
        return
    db.set_hw_archived(hid, False)
    await cb.answer("♻️ Восстановлено")
    h = db.hw_by_id(hid)
    await cb.message.edit_text(hw_full_html(h), reply_markup=hw_item_kb(h))


@router.callback_query(F.data.startswith("adm:hw:delc:"))
async def hw_del_confirm(cb: CallbackQuery):
    hid = _int(cb.data.split(":")[3])
    if hid is None:
        await cb.answer()
        return
    await cb.answer()
    await cb.message.edit_text(
        "🗑 Удалить задание полностью?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"adm:hw:del:{hid}")],
                [InlineKeyboardButton(text="◀ Отмена", callback_data=f"adm:hw:i:{hid}")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adm:hw:del:"))
async def hw_delete(cb: CallbackQuery):
    hid = _int(cb.data.split(":")[3])
    if hid is None:
        await cb.answer()
        return
    db.delete_hw(hid)
    await cb.answer("Удалено")
    await cb.message.edit_text("📚 <b>Управление ДЗ</b>", reply_markup=hw_admin_kb())


@router.callback_query(F.data.startswith("adm:hw:d:"))
async def hw_list_items(cb: CallbackQuery):
    disc_id = _int(cb.data.split(":")[3])
    if disc_id is None:
        await cb.answer()
        return
    await cb.answer()
    try:
        await cb.message.edit_text("📋 Задания дисциплины:", reply_markup=hw_items_kb(disc_id, 0))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("adm:hw:i:"))
async def hw_item(cb: CallbackQuery):
    hid = _int(cb.data.split(":")[3])
    if hid is None:
        await cb.answer()
        return
    h = db.hw_by_id(hid)
    if h is None:
        await cb.answer("Не найдено", show_alert=True)
        return
    await cb.answer()
    try:
        await cb.message.edit_text(hw_full_html(h), reply_markup=hw_item_kb(h))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("adm:hw:e:"))
async def hw_edit_menu(cb: CallbackQuery):
    hid = _int(cb.data.split(":")[3])
    if hid is None:
        await cb.answer()
        return
    await cb.answer()
    try:
        await cb.message.edit_text("✏️ Что изменить?", reply_markup=hw_edit_fields_kb(hid))
    except TelegramBadRequest:
        pass


# ------------------------------------------------------------------ новое ДЗ (мастер)

@router.callback_query(F.data.startswith("hwd:disc:"))
async def hw_new_disc(cb: CallbackQuery, state: FSMContext):
    did = _int(cb.data.split(":")[2])
    if did is None:
        await cb.answer()
        return
    disc = db.discipline_by_id(did)
    if disc is None:
        await cb.answer("Не найдена", show_alert=True)
        return
    await state.update_data(draft={"disc_id": did, "files": []})
    await state.set_state(HwNewSG.title)
    await cb.answer()
    await cb.message.edit_text(
        f"2/6 {disc['emoji']} <b>{su.esc(disc['name'])}</b>\n\nВведите название ДЗ:\n<i>/cancel — отмена</i>"
    )


@router.message(HwNewSG.title, F.text & ~F.text.startswith("/"))
async def hw_new_title(m: Message, state: FSMContext):
    data = await state.get_data()
    draft = data.get("draft") or {}
    draft["title"] = (m.text or "").strip()
    await state.update_data(draft=draft)
    await state.set_state(HwNewSG.task)
    await m.answer("3/6 Введите текст задания (что нужно сделать):")


@router.message(HwNewSG.task, F.text & ~F.text.startswith("/"))
async def hw_new_task(m: Message, state: FSMContext):
    data = await state.get_data()
    draft = data.get("draft") or {}
    draft["task"] = (m.text or "").strip()
    await state.update_data(draft=draft)
    options = su.next_lesson_options(draft["disc_id"])
    await state.update_data(due_options=options)
    await state.set_state(HwNewSG.due)
    if options:
        await m.answer(
            "4/6 Дата сдачи — ближайшие пары дисциплины:",
            reply_markup=due_options_kb(options, "hwd:due", "hwd:due:c"),
        )
    else:
        await m.answer("4/6 Введите дату сдачи в формате DD.MM.YYYY:")
        await state.set_state(HwNewSG.input)
        await state.update_data(field="due")


@router.callback_query(HwNewSG.due, F.data == "hwd:due:c")
async def hw_new_due_custom(cb: CallbackQuery, state: FSMContext):
    await state.set_state(HwNewSG.input)
    await state.update_data(field="due")
    await cb.answer()
    await cb.message.edit_text("4/6 Введите дату сдачи в формате DD.MM.YYYY:")


@router.callback_query(HwNewSG.due, F.data.startswith("hwd:due:"))
async def hw_new_due(cb: CallbackQuery, state: FSMContext):
    i = _int(cb.data.split(":")[2])
    data = await state.get_data()
    options = data.get("due_options") or []
    if i is None or i >= len(options):
        await cb.answer("Ошибка", show_alert=True)
        return
    o = options[i]
    draft = data.get("draft") or {}
    draft["due"], draft["due_type"] = o["date"], o["type"]
    await state.update_data(draft=draft)
    await state.set_state(HwNewSG.expl)
    await cb.answer()
    await cb.message.edit_text("5/6 Введите пояснение или «-», если его нет:")


@router.message(HwNewSG.expl, F.text & ~F.text.startswith("/"))
async def hw_new_expl(m: Message, state: FSMContext):
    data = await state.get_data()
    draft = data.get("draft") or {}
    text = (m.text or "").strip()
    draft["expl"] = None if text in ("-", "—") else text
    await state.update_data(draft=draft)
    await state.set_state(HwNewSG.files)
    msg = await m.answer(
        "6/6 📎 Прикрепите файлы (фото, видео, документы…) по одному сообщению,\n"
        "либо нажмите «✅ Без файлов»:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Без файлов", callback_data="hwd:nof")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="hwd:cancel")],
            ]
        ),
    )
    await state.update_data(fmsg=msg.message_id, ok_cb="hwd:fok")


@router.message(HwNewSG.files, F.document | F.photo | F.video | F.audio | F.animation | F.voice | F.video_note)
async def hw_files_attach(m: Message, state: FSMContext):
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
        f"📎 Файл «{su.esc(desc['name'])}» добавлен. Всего: <b>{len(files)}</b>.\n"
        "Можно добавить ещё или нажмите «✅ Готово».",
        reply_markup=files_wait_kb(data.get("ok_cb") or "hwd:fok"),
    )
    await state.update_data(files=files, fmsg=msg.message_id)


@router.callback_query(HwNewSG.files, F.data == "hwd:nof")
async def hw_files_none(cb: CallbackQuery, state: FSMContext):
    await state.update_data(files=[])
    await cb.answer()
    await show_preview(cb, state)


@router.callback_query(HwNewSG.files, F.data == "hwd:fok")
async def hw_files_done(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    if data.get("fmsg"):
        try:
            await cb.bot.delete_message(cb.message.chat.id, data["fmsg"])
        except TelegramAPIError:
            pass
    if data.get("hw_id"):
        db.update_hw(data["hw_id"], files=data.get("files") or [])
        h = db.hw_by_id(data["hw_id"])
        await state.clear()
        await cb.message.answer("✅ Файлы обновлены.")
        await cb.message.answer(hw_full_html(h), reply_markup=hw_item_kb(h))
        try:
            await cb.message.delete()
        except TelegramAPIError:
            pass
        return
    await show_preview(cb, state)


# ------------------------------------------------------------------ предпросмотр / публикация

@router.callback_query(HwNewSG.preview, F.data == "hwd:pub")
async def hw_publish(cb: CallbackQuery, state: FSMContext, student: dict):
    data = await state.get_data()
    draft = data.get("draft") or {}
    files = data.get("files") or draft.get("files") or []
    marked = set(data.get("fdel") or [])
    files = [f for i, f in enumerate(files) if i not in marked]
    hid = db.create_hw(
        draft["disc_id"], draft.get("title") or "—", draft.get("task") or "—",
        draft.get("due"), draft.get("due_type"), draft.get("expl"), files,
        draft.get("pub") or su.ts(), (student or {}).get("id"),
    )
    await state.clear()
    h = db.hw_by_id(hid)
    sent = 0
    for st in db.authorized_students():
        try:
            await cb.bot.send_message(
                st["tg_id"],
                hw_notice_html(h, {"name": h["discipline"], "emoji": h["emoji"]}),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Открыть", callback_data=f"hw:v:{hid}")]]
                ),
            )
            sent += 1
        except TelegramAPIError:
            continue
    await cb.answer("Опубликовано!")
    try:
        await cb.message.edit_text(
            f"✅ <b>ДЗ опубликовано</b>\nОтправлено студентам: {sent}\n\n" + hw_full_html(h),
            reply_markup=hw_admin_kb(),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(HwNewSG.preview, F.data == "hwd:rf")
async def refill_menu(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text("🔄 <b>Что поменять?</b>", reply_markup=refill_kb())
    except TelegramBadRequest:
        pass


@router.callback_query(HwNewSG.preview, F.data == "hwd:rf:back")
async def preview_back(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await cb.answer()
    try:
        await cb.message.edit_text(draft_preview_html(data.get("draft") or {}), reply_markup=preview_kb())
    except TelegramBadRequest:
        pass


@router.callback_query(HwNewSG.preview, F.data == "hwd:rf:due")
async def refill_due(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    draft = data.get("draft") or {}
    options = su.next_lesson_options(draft.get("disc_id"))
    await state.update_data(due_options=options)
    await state.set_state(HwNewSG.due)
    await cb.answer()
    if options:
        await cb.message.edit_text(
            "📅 Дата сдачи:", reply_markup=due_options_kb(options, "hwd:due", "hwd:due:c")
        )
    else:
        await state.set_state(HwNewSG.input)
        await state.update_data(field="due")
        await cb.message.edit_text("Введите дату сдачи DD.MM.YYYY:")


@router.callback_query(HwNewSG.preview, F.data == "hwd:rf:disc")
async def refill_disc(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text("Выберите дисциплину:", reply_markup=disc_grid_kb("hwd:rdisc"))


@router.callback_query(F.data.startswith("hwd:rdisc:"))
async def refill_disc_set(cb: CallbackQuery, state: FSMContext):
    did = _int(cb.data.split(":")[2])
    if did is None:
        await cb.answer()
        return
    data = await state.get_data()
    draft = data.get("draft") or {}
    draft["disc_id"] = did
    await state.update_data(draft=draft)
    await cb.answer("Дисциплина обновлена")
    await show_preview(cb, state, edit_message=cb.message)


@router.callback_query(HwNewSG.preview, F.data == "hwd:rf:files")
async def refill_files(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    draft = data.get("draft") or {}
    files = draft.get("files") or []
    await state.update_data(files=files, fdel=[])
    await cb.answer()
    try:
        await cb.message.edit_text(
            "📎 Управление файлами (нажмите, чтобы пометить на удаление):",
            reply_markup=files_manage_kb(files, set(), "hwd:fdel", "hwd:fadd", "hwd:fok2", "hwd:rf:back"),
        )
    except TelegramBadRequest:
        pass


# generic «hwd:rf:{поле}» — после точных (due/disc/files/back)
@router.callback_query(HwNewSG.preview, F.data.startswith("hwd:rf:"))
async def refill_field(cb: CallbackQuery, state: FSMContext):
    field = cb.data.split(":")[2]
    if field not in ("title", "task", "expl", "pub"):
        await cb.answer()
        return
    await state.set_state(HwNewSG.input)
    await state.update_data(field=field, mode="refill", hw_id=None)
    prompts = {
        "title": "Введите название:",
        "task": "Введите текст задания:",
        "expl": "Введите пояснение или «-»:",
        "pub": "Введите дату публикации DD.MM.YYYY или DD.MM.YYYY ЧЧ:ММ:",
    }
    await cb.answer()
    await cb.message.edit_text(prompts[field])


@router.callback_query(F.data.startswith("hwd:fdel:"))
async def draft_file_toggle(cb: CallbackQuery, state: FSMContext):
    i = _int(cb.data.split(":")[2])
    data = await state.get_data()
    files = data.get("files") or []
    marked = set(data.get("fdel") or [])
    if i is None or i >= len(files):
        await cb.answer()
        return
    marked.symmetric_difference_update({i})
    await state.update_data(fdel=sorted(marked))
    await cb.answer("🗑 Помечено на удаление" if i in marked else "↩️ Оставить")
    try:
        await cb.message.edit_text(
            "📎 Управление файлами:",
            reply_markup=files_manage_kb(files, marked, "hwd:fdel", "hwd:fadd", "hwd:fok2", "hwd:rf:back"),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "hwd:fadd")
async def draft_files_add(cb: CallbackQuery, state: FSMContext):
    await state.set_state(HwNewSG.files)
    await state.update_data(ok_cb="hwd:fok2")
    msg = await cb.message.edit_text(
        "➕ Прикрепите файлы сообщениями, затем «✅ Готово»:", reply_markup=files_wait_kb("hwd:fok2")
    )
    await state.update_data(fmsg=msg.message_id if hasattr(msg, "message_id") else None)
    await cb.answer()


@router.callback_query(F.data == "hwd:fok2")
async def draft_files_apply(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("fmsg"):
        try:
            await cb.bot.delete_message(cb.message.chat.id, data["fmsg"])
        except TelegramAPIError:
            pass
    files = data.get("files") or []
    marked = set(data.get("fdel") or [])
    files = [f for i, f in enumerate(files) if i not in marked]
    draft = data.get("draft") or {}
    draft["files"] = files
    await state.update_data(draft=draft, files=[], fdel=[])
    await cb.answer()
    await show_preview(cb, state, edit_message=cb.message)


@router.callback_query(F.data == "hwd:cancel")
async def hw_cancel(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("fmsg"):
        try:
            await cb.bot.delete_message(cb.message.chat.id, data["fmsg"])
        except TelegramAPIError:
            pass
    await state.clear()
    await cb.answer("Отменено")
    try:
        await cb.message.edit_text("📚 <b>Управление ДЗ</b>", reply_markup=hw_admin_kb())
    except TelegramBadRequest:
        pass


# ------------------------------------------------------------------ ввод полей (общий)

@router.message(HwNewSG.input, F.text & ~F.text.startswith("/"))
async def hw_field_input(m: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("field")
    text = (m.text or "").strip()
    draft = data.get("draft") or {}
    mode = data.get("mode")

    async def to_preview():
        await show_preview(None, state, bot=m.bot, chat_id=m.chat.id)

    if field == "due":
        d = su.parse_dmY(text)
        if d is None:
            await m.answer("⚠️ Неверный формат. Введите дату как DD.MM.YYYY (например, 27.10.2026):")
            return
        draft["due"], draft["due_type"] = d.isoformat(), None
        await state.update_data(draft=draft)
        if data.get("hw_id"):
            return await edit_done(m, state, data["hw_id"])
        if mode == "refill":
            return await to_preview()
        await state.set_state(HwNewSG.expl)
        await m.answer("5/6 Введите пояснение или «-», если его нет:")
        return

    if field in ("title", "task"):
        draft[field] = text
        await state.update_data(draft=draft)
        if data.get("hw_id"):
            return await edit_done(m, state, data["hw_id"])
        if mode == "refill":
            return await to_preview()
        if field == "title":
            await state.set_state(HwNewSG.task)
            await m.answer("3/6 Введите текст задания:")
        return

    if field == "expl":
        draft["expl"] = None if text in ("-", "—") else text
        await state.update_data(draft=draft)
        if data.get("hw_id"):
            return await edit_done(m, state, data["hw_id"])
        if mode == "refill":
            return await to_preview()
        await state.set_state(HwNewSG.files)
        msg = await m.answer(
            "6/6 📎 Прикрепите файлы по одному сообщению, либо «✅ Без файлов»:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Без файлов", callback_data="hwd:nof")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="hwd:cancel")],
                ]
            ),
        )
        await state.update_data(fmsg=msg.message_id, ok_cb="hwd:fok")
        return

    if field == "pub":
        dt = su.parse_dt(text)
        if dt is None:
            await m.answer("⚠️ Формат: DD.MM.YYYY или DD.MM.YYYY ЧЧ:ММ:")
            return
        draft["pub"] = dt.strftime("%Y-%m-%d %H:%M")
        await state.update_data(draft=draft)
        if data.get("hw_id"):
            return await edit_done(m, state, data["hw_id"])
        return await to_preview()

    await m.answer("⚠️ Неизвестное поле. /cancel")


# ------------------------------------------------------------------ редактирование существующих

@router.callback_query(F.data.startswith("adm:hw:f:"))
async def hw_edit_field(cb: CallbackQuery, state: FSMContext):
    """adm:hw:f:{id}:{field} — единый диспетчер всех полей существующего ДЗ."""
    parts = cb.data.split(":")
    if len(parts) != 5:
        await cb.answer()
        return
    hid, field = _int(parts[3]), parts[4]
    if hid is None:
        await cb.answer()
        return
    h = db.hw_by_id(hid)
    if h is None:
        await cb.answer("Не найдено", show_alert=True)
        return
    await cb.answer()

    if field in ("title", "task", "expl", "pub"):
        await state.set_state(HwNewSG.input)
        await state.update_data(hw_id=hid, field=field, draft={"disc_id": h["discipline_id"]}, files=[], fdel=[])
        prompts = {
            "title": "Введите новое название:",
            "task": "Введите новый текст задания:",
            "expl": "Введите пояснение или «-» чтобы убрать:",
            "pub": "Введите дату публикации DD.MM.YYYY [ЧЧ:ММ]:",
        }
        await cb.message.edit_text(prompts[field])
        return

    if field == "due":
        options = su.next_lesson_options(h["discipline_id"])
        await state.set_state(HwNewSG.due)
        await state.update_data(hw_id=hid, draft={"disc_id": h["discipline_id"]}, due_options=options)
        if options:
            await cb.message.edit_text(
                "📅 Новый срок сдачи:", reply_markup=due_options_kb(options, f"ahwd:{hid}", f"ahwdc:{hid}")
            )
        else:
            await state.set_state(HwNewSG.input)
            await state.update_data(field="due")
            await cb.message.edit_text("Введите дату сдачи DD.MM.YYYY:")
        return

    if field == "disc":
        await cb.message.edit_text("Выберите дисциплину:", reply_markup=disc_grid_kb(f"ahws:{hid}"))
        return

    if field == "files":
        files = json.loads(h.get("files") or "[]")
        await state.set_state(HwNewSG.preview)
        await state.update_data(hw_id=hid, files=files, fdel=[], draft={"disc_id": h["discipline_id"]})
        await cb.message.edit_text(
            "📎 Управление файлами (нажмите, чтобы пометить на удаление):",
            reply_markup=files_manage_kb(files, set(), f"ahwfd:{hid}", f"ahwfa:{hid}", f"ahwfw:{hid}", f"adm:hw:i:{hid}"),
        )
        return

    await cb.answer("Неизвестное поле", show_alert=True)


@router.callback_query(HwNewSG.due, F.data.startswith("ahwd:"))
async def hw_edit_due_pick(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")  # ahwd:{hid}:{i}
    if len(parts) != 3:
        await cb.answer()
        return
    hid, i = _int(parts[1]), _int(parts[2])
    data = await state.get_data()
    options = data.get("due_options") or []
    if hid is None or i is None or i >= len(options):
        await cb.answer("Ошибка", show_alert=True)
        return
    o = options[i]
    db.update_hw(hid, due_date=o["date"], due_type=o["type"])
    h = db.hw_by_id(hid)
    await state.clear()
    await cb.answer("Срок обновлён")
    await cb.message.edit_text(hw_full_html(h), reply_markup=hw_item_kb(h))


@router.callback_query(HwNewSG.due, F.data.startswith("ahwdc:"))
async def hw_edit_due_custom(cb: CallbackQuery, state: FSMContext):
    hid = _int(cb.data.split(":")[1])
    if hid is None:
        await cb.answer()
        return
    h = db.hw_by_id(hid)
    if h is None:
        await cb.answer("Не найдено", show_alert=True)
        return
    await state.set_state(HwNewSG.input)
    await state.update_data(hw_id=hid, field="due", draft={"disc_id": h["discipline_id"]})
    await cb.answer()
    await cb.message.edit_text("Введите дату сдачи DD.MM.YYYY:")


@router.callback_query(F.data.startswith("ahws:"))
async def hw_edit_disc_set(cb: CallbackQuery):
    parts = cb.data.split(":")  # ahws:{hid}:{did}
    if len(parts) != 3:
        await cb.answer()
        return
    hid, did = _int(parts[1]), _int(parts[2])
    if hid is None or did is None:
        await cb.answer()
        return
    db.update_hw(hid, discipline_id=did)
    h = db.hw_by_id(hid)
    await cb.answer("Дисциплина обновлена")
    await cb.message.edit_text(hw_full_html(h), reply_markup=hw_item_kb(h))


@router.callback_query(F.data.startswith("ahwfd:"))
async def hw_edit_file_toggle(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")  # ahwfd:{hid}:{i}
    if len(parts) != 3:
        await cb.answer()
        return
    hid, i = _int(parts[1]), _int(parts[2])
    data = await state.get_data()
    files = data.get("files") or []
    marked = set(data.get("fdel") or [])
    if hid is None or i is None or i >= len(files):
        await cb.answer()
        return
    marked.symmetric_difference_update({i})
    await state.update_data(fdel=sorted(marked))
    await cb.answer("🗑 Помечено" if i in marked else "↩️ Оставить")
    try:
        await cb.message.edit_text(
            "📎 Управление файлами:",
            reply_markup=files_manage_kb(files, marked, f"ahwfd:{hid}", f"ahwfa:{hid}", f"ahwfw:{hid}", f"adm:hw:i:{hid}"),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("ahwfa:"))
async def hw_edit_files_add(cb: CallbackQuery, state: FSMContext):
    hid = _int(cb.data.split(":")[1])
    if hid is None:
        await cb.answer()
        return
    await state.set_state(HwNewSG.files)
    await state.update_data(hw_id=hid, ok_cb="hwd:fok")
    await cb.answer()
    msg = await cb.message.edit_text(
        "➕ Прикрепите файлы сообщениями, затем «✅ Готово»:", reply_markup=files_wait_kb("hwd:fok")
    )
    await state.update_data(fmsg=msg.message_id if hasattr(msg, "message_id") else None)


@router.callback_query(F.data.startswith("ahwfw:"))
async def hw_edit_files_apply(cb: CallbackQuery, state: FSMContext):
    hid = _int(cb.data.split(":")[1])
    if hid is None:
        await cb.answer()
        return
    data = await state.get_data()
    files = data.get("files") or []
    marked = set(data.get("fdel") or [])
    files = [f for i, f in enumerate(files) if i not in marked]
    db.update_hw(hid, files=files)
    h = db.hw_by_id(hid)
    await state.clear()
    await cb.answer("Файлы обновлены")
    await cb.message.edit_text(hw_full_html(h), reply_markup=hw_item_kb(h))
