"""Раздел «Домашнее задание» для студентов."""
import json

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from .. import db
from ..keyboards import (
    hw_detail_kb,
    hw_done_list_kb,
    hw_list_kb,
    hw_menu_new_kb,
)
from ..services import schedule_utils as su

router = Router()


async def send_files_aiogram(bot: Bot, chat_id: int, files_json: str) -> int:
    sent = 0
    for f in json.loads(files_json or "[]"):
        try:
            t, fid = f.get("type"), f["file_id"]
            if t == "photo":
                await bot.send_photo(chat_id, fid)
            elif t == "video":
                await bot.send_video(chat_id, fid)
            elif t == "audio":
                await bot.send_audio(chat_id, fid)
            elif t == "animation":
                await bot.send_animation(chat_id, fid)
            elif t == "voice":
                await bot.send_voice(chat_id, fid)
            elif t == "video_note":
                await bot.send_video_note(chat_id, fid)
            else:
                await bot.send_document(chat_id, fid)
            sent += 1
        except TelegramAPIError:
            continue
    return sent


def hw_detail_html(hw: dict) -> str:
    lines = [
        f"📚 {hw['emoji']} <b>{su.esc(hw['discipline'])}</b>",
        "",
        f"🏷 <b>{su.esc(hw['title'])}</b>",
        f"📝 Задание: {su.esc(hw['task_text'])}",
    ]
    if hw.get("due_date"):
        due = f"📅 Сдать до: {su.fmt_dmy(hw['due_date'])} ({su.wd_lower(hw['due_date'])})"
        if hw.get("due_type"):
            due += f", к паре ({hw['due_type']})"
        lines.append(due)
    pub = hw.get("published_at") or ""
    if pub:
        lines.append(f"🕐 Опубликовано: {pub[8:10]}.{pub[5:7]}, {pub[11:16]}")
    if hw.get("explanation"):
        lines.append(f"💡 Пояснение: {su.esc(hw['explanation'])}")
    files = json.loads(hw.get("files") or "[]")
    if files:
        names = ", ".join(su.esc(f.get("name") or "файл") for f in files)
        lines.append(f"📎 Материалов: {len(files)} ({names})")
    return "\n".join(lines)


async def open_homework(cb: CallbackQuery, student: dict):
    hid = int(cb.data.split(":")[2])
    hw = db.hw_by_id(hid)
    if hw is None:
        await cb.answer("Задание не найдено", show_alert=True)
        return
    await cb.answer()
    db.mark_viewed(student["id"], hid, su.ts())
    if cb.message:
        try:
            await cb.message.delete()
        except TelegramAPIError:
            pass
    await send_files_aiogram(cb.bot, cb.from_user.id, hw.get("files") or "[]")
    done = hid in db.done_hw_ids(student["id"])
    await cb.bot.send_message(
        cb.from_user.id,
        hw_detail_html(hw),
        reply_markup=hw_detail_kb(hid, hw["discipline_id"], done),
    )


@router.callback_query(F.data == "hw")
async def hw_menu(cb: CallbackQuery, student: dict):
    await cb.answer()
    unviewed = db.unviewed_hw_ids(student["id"])
    kb = hw_menu_new_kb(unviewed) if unviewed else hw_menu_new_kb(set())
    text = (
        "📚 <b>Домашнее задание</b>\n\nВыберите дисциплину."
        if db.active_homework()
        else "📚 <b>Домашнее задание</b>\n\n📭 Актуальных заданий нет."
    )
    try:
        await cb.message.edit_text(text + "\n\n✳️ — есть непросмотренное", reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("hw:") & F.data.regexp_match(r"^hw:\d+$"))
async def hw_disc(cb: CallbackQuery, student: dict):
    disc_id = int(cb.data.split(":")[1])
    disc = db.discipline_by_id(disc_id)
    if disc is None:
        await cb.answer("Дисциплина не найдена", show_alert=True)
        return
    await cb.answer()
    done = db.done_hw_ids(student["id"])
    try:
        await cb.message.edit_text(
            f"{disc['emoji']} <b>{su.esc(disc['name'])}</b> — задания:",
            reply_markup=hw_list_kb(disc_id, done),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("hw:v:"))
async def hw_view(cb: CallbackQuery, student: dict):
    await open_homework(cb, student)


@router.callback_query(F.data.startswith("hw:done:"))
async def hw_toggle_done(cb: CallbackQuery, student: dict):
    hid = int(cb.data.split(":")[2])
    hw = db.hw_by_id(hid)
    if hw is None:
        await cb.answer("Задание не найдено", show_alert=True)
        return
    done = hid in db.done_hw_ids(student["id"])
    db.set_hw_done(student["id"], hid, not done, su.ts())
    await cb.answer("✅ Отмечено выполненным" if not done else "↩️ Вернуто в работу")
    try:
        await cb.message.edit_text(
            hw_detail_html(hw),
            reply_markup=hw_detail_kb(hid, hw["discipline_id"], not done),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "hw:dl")
async def hw_done_list(cb: CallbackQuery, student: dict):
    await cb.answer()
    rows = db.q(
        "SELECT h.id, h.title, h.due_date, h.archived, d.name AS discipline, d.emoji "
        "FROM homework_done hd JOIN homework h ON h.id = hd.homework_id "
        "JOIN disciplines d ON d.id = h.discipline_id WHERE hd.student_id = ? "
        "ORDER BY h.archived, h.due_date",
        (student["id"],),
    )
    if rows:
        items = "\n".join(
            f"{'📦' if r['archived'] else '✅'} {r['emoji']} {su.esc(r['discipline'])} — "
            f"«{su.esc(r['title'])}» (до {su.fmt_dm(r['due_date']) if r['due_date'] else '—'})"
            for r in rows
        )
        text = f"📥 <b>Выполненные ДЗ</b>\n\n{items}\n\n<i>Нажмите на задание ниже, чтобы открыть/вернуть.</i>"
    else:
        text = "📥 <b>Выполненные ДЗ</b>\n\n📭 Пока ничего не отмечено."
    try:
        await cb.message.edit_text(text, reply_markup=hw_done_list_kb(student["id"]))
    except TelegramBadRequest:
        pass
