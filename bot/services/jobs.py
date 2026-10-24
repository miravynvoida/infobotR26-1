"""Фоновые задачи: опрос посещаемости, напоминания о парах, расписание на завтра, архивация ДЗ."""
import asyncio
import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .. import config, db
from . import attendance as att_svc
from . import schedule_utils as su

log = logging.getLogger("bot.jobs")


def _same_hm(a, b) -> bool:
    return a.hour == b.hour and a.minute == b.minute


async def _safe_send(bot: Bot, chat_id: int, **kwargs):
    try:
        return await bot.send_message(chat_id, **kwargs)
    except TelegramAPIError as e:
        log.warning("Не отправилось %s: %s", chat_id, e)
        return None


def attendance_ask_kb(day_iso: str):
    from ..keyboards import attendance_kb

    return attendance_kb(day_iso)


async def send_attendance_ask(bot: Bot, st: dict, day_iso: str, first_start: str):
    n_pairs = len(db.day_lessons(day_iso))
    text = (
        f"👋 <b>Сегодня {n_pairs} пар(ы). Первая — в {first_start}.</b>\n\n"
        "Будете ли вы сегодня на парах?\n"
        "<i>Ответ видят староста и зам старосты.</i>"
    )
    await _safe_send(bot, st["tg_id"], text=text, reply_markup=attendance_ask_kb(day_iso))


async def tick(bot: Bot) -> None:
    n = su.now()
    day = su.iso(n.date())
    lessons = db.day_lessons(day)

    # --- опрос посещаемости: вопрос за 60 мин, напоминания, сводка за 5 мин
    if lessons:
        first = lessons[0]
        first_dt = su.dt_on(day, first["start"])

        ask_dt = first_dt - timedelta(minutes=config.cfg.attendance_ask_minutes)
        if _same_hm(n, ask_dt):
            for st in db.authorized_students():
                if db.get_attendance(day, st["id"]):
                    continue
                if db.notif_once(day, "att_ask", str(st["tg_id"])):
                    await send_attendance_ask(bot, st, day, first["start"])

        for off in config.cfg.attendance_remind_minutes:
            rem_dt = first_dt - timedelta(minutes=off)
            if _same_hm(n, rem_dt):
                for st in db.authorized_students():
                    if db.get_attendance(day, st["id"]):
                        continue
                    if db.notif_once(day, "att_rem", f"{st['tg_id']}:{off}"):
                        await _safe_send(
                            bot,
                            st["tg_id"],
                            text=(
                                "⏰ <b>Напоминание</b>\n"
                                f"До первой пары {off} мин. Ответьте, пожалуйста, будете ли вы сегодня:\n"
                                "<i>вопрос выше ↑</i>"
                            ),
                            reply_markup=attendance_ask_kb(day),
                        )

        sum_dt = first_dt - timedelta(minutes=config.cfg.attendance_summary_minutes)
        if _same_hm(n, sum_dt) and db.notif_once(day, "att_sum", "all"):
            text = att_svc.summary_html(day)
            for tg_id in config.cfg.staff_ids:
                await _safe_send(bot, tg_id, text=text)

    # --- напоминания о парах (перед каждой парой, у каждого своя настройка)
    if lessons:
        now_inside_lesson = any(
            su.dt_on(day, ls["start"]) <= n < su.dt_on(day, ls["end"]) for ls in lessons
        )
        for ls in lessons:
            start_dt = su.dt_on(day, ls["start"])
            for s in db.all_notify_settings():
                if not s["next_pair"] or n >= start_dt:
                    continue
                if s.get("quiet") and now_inside_lesson:
                    continue  # «тихая пара»: во время занятия не дёргаем
                target = start_dt - timedelta(minutes=s["next_pair_min"])
                if _same_hm(n, target) and db.notif_once(
                    day, "pair", f"{ls['pair_no']}:{s['tg_id']}:{s['next_pair_min']}"
                ):
                    brief = f"{ls['emoji']} <b>{su.esc(ls['discipline'])}</b>"
                    if ls.get("lesson_type"):
                        brief += f" ({ls['lesson_type']})"
                    room = f", ауд. {su.esc(ls['room'])}" if ls.get("room") else ""
                    text = (
                        f"⏰ <b>Через {su.hm_ru(s['next_pair_min'])} — пара</b>\n"
                        f"{ls['pair_no']} пара • {ls['start']}–{ls['end']}{room}\n"
                        f"{brief}"
                    )
                    await _safe_send(bot, s["tg_id"], text=text)

    # --- напоминания о ДЗ на завтра (независимые, своё время)
    tomorrow_iso = su.iso(n.date() + timedelta(days=1))
    hw_due = db.hw_due_on(tomorrow_iso)
    for s in db.all_notify_settings():
        if not hw_due or not s.get("hw_tomorrow"):
            continue
        tt = su.parse_hm(s.get("hw_tomorrow_time") or "18:00")
        if tt and _same_hm(n.time(), tt) and db.notif_once(day, "hw_tmrw", str(s["tg_id"])):
            text = "📚 <b>ДЗ к завтрашнему дню:</b>\n" + "\n".join(
                f"• {h['emoji']} {su.esc(h['discipline'])} — «{su.esc(h['title'])}»"
                f" (до {su.fmt_dm(h['due_date'])})" for h in hw_due
            )
            await _safe_send(bot, s["tg_id"], text=text)

    # --- расписание на завтра (у каждого своё время)
    tomorrow = su.iso(n.date() + timedelta(days=1))
    tmrw_lessons = db.day_lessons(tomorrow)
    if tmrw_lessons:
        for s in db.all_notify_settings():
            if not s["tomorrow"]:
                continue
            tt = su.parse_hm(s["tomorrow_time"])
            if tt and _same_hm(n.time(), tt) and db.notif_once(day, "tmrw", str(s["tg_id"])):
                d = su.today() + timedelta(days=1)
                text = (
                    f"📅 <b>Расписание на завтра — {su.WEEKDAYS_FULL[d.weekday()]}, {su.fmt_dmy(d)}</b>\n\n"
                    + "\n\n".join(su.lesson_block_html(ls) for ls in tmrw_lessons)
                )
                due = db.hw_due_on(tomorrow)
                if due:
                    text += "\n\n📚 <b>ДЗ к завтрашнему дню:</b>\n" + "\n".join(
                        f"• {h['emoji']} {su.esc(h['discipline'])} — «{su.esc(h['title'])}»" for h in due
                    )
                await _safe_send(bot, s["tg_id"], text=text)


async def archive_due_homework() -> None:
    day = su.iso(su.today())
    cnt = db.archive_due_homework(day, su.ts())
    if cnt:
        log.info("Архивировано ДЗ со сроком %s: %d", day, cnt)


def make_scheduler(bot: Bot) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=su.TZ)
    sched.add_job(tick, CronTrigger(second=0, timezone=su.TZ), args=(bot,), id="tick")
    hh, mm = config.cfg.hw_archive_time.split(":")
    sched.add_job(
        archive_due_homework,
        CronTrigger(hour=int(hh), minute=int(mm), timezone=su.TZ),
        id="hw_archive",
    )
    return sched
