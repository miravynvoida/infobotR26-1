"""Режимы «Технические работы» и «Контрольная неделя» (хранятся в kv)."""
from .. import db
from . import schedule_utils as su


def maintenance_state() -> dict:
    until = db.kv_get("maintenance_until", "")
    return {"on": bool(until), "until": until}


def maintenance_text() -> str:
    st = maintenance_state()
    if not st["on"]:
        return ""
    if st["until"]:
        u = st["until"]  # DD.MM.YYYY HH:MM
        return f"🛠 Ведутся технические работы до {u}. Скоро всё вернётся!"
    return "🛠 Ведутся технические работы. Скоро всё вернётся!"


def set_maintenance(until_dt) -> None:
    """until_dt: datetime | None (None = бессрочно)."""
    db.kv_set("maintenance_until", until_dt.strftime("%d.%m.%Y %H:%M") if until_dt else "-")


def stop_maintenance() -> None:
    db.kv_delete("maintenance_until")


def exam_week_state() -> bool:
    return db.kv_get("exam_week", "0") == "1"


def set_exam_week(on: bool) -> None:
    db.kv_set("exam_week", "1" if on else "0")


def risk_disciplines(sid: int) -> list[int]:
    """Дисциплины с риском неаттестации: средний ≤ 2,5 или Н > 50% прошедших пар."""
    from datetime import date

    today_iso = su.iso(su.today())
    past_pairs: dict[int, int] = {}
    for d in db.schedule_dates():
        if d > today_iso:
            continue
        for ls in db.day_lessons(d):
            if su.dt_on(d, ls["end"]) > su.now():
                continue
            past_pairs[ls["discipline_id"]] = past_pairs.get(ls["discipline_id"], 0) + 1
    risk = []
    for disc in db.all_disciplines():
        rows = db.q(
            "SELECT value FROM grades WHERE student_id=? AND discipline_id=?", (sid, disc["id"])
        )
        vals = [r["value"] for r in rows]
        nums = [int(v) for v in vals if v in ("2", "3", "4", "5")]
        skips = vals.count("Н")
        avg = round(sum(nums) / len(nums), 2) if nums else None
        pairs = past_pairs.get(disc["id"], 0)
        if (avg is not None and avg <= 2.5) or (pairs > 0 and skips / pairs > 0.5):
            risk.append(disc["id"])
    return risk
