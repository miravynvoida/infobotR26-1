"""Посещаемость: опрос, сводка для старосты/замов/админов."""
import json
from datetime import date, datetime, timedelta

from .. import config, db
from . import schedule_utils as su


def ask_active(n: datetime | None = None) -> dict | None:
    """Активен ли опрос «будете ли вы сегодня на парах»: от времени вопроса
    до конца последней пары дня (весь день можно изменить ответ)."""
    n = n or su.now()
    day = su.iso(n.date())
    lessons = db.day_lessons(day)
    if not lessons:
        return None
    first = su.dt_on(day, lessons[0]["start"])
    last_end = su.dt_on(day, lessons[-1]["end"])
    ask_at = first - timedelta(minutes=config.cfg.attendance_ask_minutes)
    if ask_at <= n <= last_end:
        return {"date": day, "first_start": lessons[0]["start"], "lessons": lessons}
    return None


def summary(day_iso: str) -> dict:
    rows = {r["student_id"]: r for r in db.day_attendance(day_iso)}
    auth = db.authorized_students()
    full, none, partial, sick, noans = 0, [], [], [], []
    for st in auth:
        r = rows.get(st["id"])
        if r is None:
            noans.append(su.short_name(st["fio"]))
        elif r["status"] == "full":
            full += 1
        elif r["status"] == "none":
            none.append(su.short_name(st["fio"]))
        elif r["status"] == "sick":
            sick.append(su.short_name(st["fio"]))
        elif r["status"] == "partial":
            missing = json.loads(r["missing_pairs"] or "[]")
            pairs = ", ".join(str(p) for p in sorted(missing)) or "—"
            partial.append((su.short_name(st["fio"]), pairs))
    return {
        "date": day_iso,
        "weekday": su.WEEKDAYS_FULL[date.fromisoformat(day_iso).weekday()],
        "full_count": full,
        "none": none,
        "partial": partial,
        "sick": sick,
        "no_answer": noans,
        "auth_total": len(auth),
    }


def summary_html(day_iso: str) -> str:
    s = summary(day_iso)
    lines = [
        f"📋 <b>Сводка посещаемости — {s['weekday']}, {su.fmt_dmy(day_iso)}</b>",
        "",
        f"✅ Будут на всех парах: {s['full_count']} чел.",
    ]
    if s["none"]:
        lines.append("\n❌ <b>Не будут (%d):</b> " % len(s["none"]) + esc_join(s["none"]))
    if s["partial"]:
        lines.append(f"\n⚖️ <b>Частично ({len(s['partial'])}):</b>")
        lines.extend(f" • {su.esc(name)} — без {pairs} пары" for name, pairs in s["partial"])
    if s["sick"]:
        lines.append(f"\n🤒 <b>Заболели ({len(s['sick'])}):</b> " + esc_join(s["sick"]))
    if s["no_answer"]:
        lines.append(f"\n❓ <b>Не ответили ({len(s['no_answer'])}):</b> " + esc_join(s["no_answer"]))
    return "\n".join(lines)


def esc_join(names: list[str]) -> str:
    return ", ".join(su.esc(n) for n in names)
