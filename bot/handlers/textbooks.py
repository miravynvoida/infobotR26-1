"""Раздел «Учебники» для студентов."""
import json

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery

from .. import db
from ..keyboards import tb_detail_kb, tb_list_kb, tb_menu_kb
from ..services import schedule_utils as su
from .homework import send_files_aiogram

router = Router()


def tb_detail_html(tb: dict) -> str:
    lines = [f"📖 {tb['emoji']} <b>{su.esc(tb['discipline'])}</b>", "", f"🏷 <b>{su.esc(tb['title'])}</b>"]
    if tb.get("description"):
        lines.append(f"📝 {su.esc(tb['description'])}")
    files = json.loads(tb.get("files") or "[]")
    if files:
        names = ", ".join(su.esc(f.get("name") or "файл") for f in files)
        lines.append(f"📎 Материалов: {len(files)} ({names})")
    return "\n".join(lines)


@router.callback_query(F.data == "tb")
async def tb_menu(cb: CallbackQuery):
    await cb.answer()
    has = bool(db.all_textbooks())
    text = (
        "📖 <b>Учебники и материалы</b>\n\nВыберите дисциплину:"
        if has
        else "📖 <b>Учебники и материалы</b>\n\n📭 Учебников пока нет."
    )
    try:
        await cb.message.edit_text(text, reply_markup=tb_menu_kb())
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp_match(r"^tb:\d+$"))
async def tb_disc(cb: CallbackQuery):
    disc_id = int(cb.data.split(":")[1])
    disc = db.discipline_by_id(disc_id)
    if disc is None:
        await cb.answer("Дисциплина не найдена", show_alert=True)
        return
    await cb.answer()
    try:
        await cb.message.edit_text(
            f"{disc['emoji']} <b>{su.esc(disc['name'])}</b> — учебники:",
            reply_markup=tb_list_kb(disc_id),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("tb:v:"))
async def tb_view(cb: CallbackQuery):
    tid = int(cb.data.split(":")[2])
    tb = db.textbook_by_id(tid)
    if tb is None:
        await cb.answer("Не найдено", show_alert=True)
        return
    await cb.answer()
    if cb.message:
        try:
            await cb.message.delete()
        except TelegramAPIError:
            pass
    await send_files_aiogram(cb.bot, cb.from_user.id, tb.get("files") or "[]")
    await cb.bot.send_message(
        cb.from_user.id,
        tb_detail_html(tb),
        reply_markup=tb_detail_kb(tid, tb["discipline_id"]),
    )
