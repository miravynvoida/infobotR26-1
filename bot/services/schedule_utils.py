"""Расписание: недели, время пар, форматирование, статусы, импорт JSON."""
import calendar as _cal
import html
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import config, db

try:
    TZ = ZoneInfo("Europe/Moscow")
except Exception:  # нет tzdata (Windows без пакета) — фиксированный UTC+3
    TZ = timezone(timedelta(hours=3), name="MSK")

WEEKDAYS_FULL = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
WEEKDAYS_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
MONTHS = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)

PAIR_TIMES = (
    ("08:30", "10:00"),
    ("10:10", "11:40"),
    ("11:50", "13:20"),
    ("13:50", "15:20"),
    ("15:30", "17:00"),
    ("17:10", "18:40"),
    ("18:50", "20:20"),
)

DISCIPLINE_ALIASES = {
    "иностранныйязык": "Ин. язык",
    "инязык": "Ин. язык",
    "основыбезопасностиизащитародины": "ОБЖиЗР",
    "основыпроектнойдеятельности": "ОПД",
    "физическаякультура": "Физ. культура",
}


def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()


def iso(d: date) -> str:
    return d.isoformat()


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)


def ts(dt: datetime | None = None) -> str:
    return (dt or now()).strftime("%Y-%m-%d %H:%M")


def t(hm: str):
    return datetime.strptime(hm, "%H:%M").time()


def dt_on(day_iso: str, hm: str) -> datetime:
    return datetime.combine(date.fromisoformat(day_iso), t(hm), TZ)


def parse_hm(s: str):
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%H:%M").time()
    except ValueError:
        return None


def parse_dmY(s: str) -> date | None:
    s = (s or "").strip().replace("-", ".")
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_dt(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def fmt_dmy(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%d.%m.%Y")


def fmt_dm(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%d.%m")


def wd_lower(day_iso: str) -> str:
    return WEEKDAYS_SHORT[date.fromisoformat(day_iso).weekday()]


def short_name(fio: str) -> str:
    parts = (fio or "").split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}."


def hm_ru(minutes: int) -> str:
    minutes = max(0, int(minutes))
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h} ч {m} мин"
    if h:
        return f"{h} ч"
    return f"{m} мин"


def fmt_avg(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


# ------------------------------------------------------------------ недели

def week1_bounds() -> tuple[date, date]:
    start = config.cfg.first_week_start
    end = start + timedelta(days=6 - start.weekday())
    return start, end


def week_bounds(n: int) -> tuple[date, date]:
    if n <= 1:
        return week1_bounds()
    _, w1_end = week1_bounds()
    start = w1_end + timedelta(days=1) + timedelta(weeks=n - 2)
    return start, start + timedelta(days=6)


def study_week(d: date) -> int | None:
    start, end = week1_bounds()
    if d < start:
        return None
    if d <= end:
        return 1
    base = end + timedelta(days=1)
    return (d - base).days // 7 + 2


def study_week_by_iso(day_iso: str) -> int | None:
    return study_week(date.fromisoformat(day_iso))


def available_weeks() -> list[dict]:
    weeks: set[int] = set()
    for d in db.schedule_dates():
        w = study_week(date.fromisoformat(d))
        if w:
            weeks.add(w)
    if not weeks:
        w = study_week(today())
        if w:
            weeks.add(w)
    out = []
    for n in sorted(weeks):
        s, e = week_bounds(n)
        out.append({"n": n, "start": iso(s), "end": iso(e), "label": f"{fmt_dm(s)} – {fmt_dm(e)}"})
    return out


# ------------------------------------------------------------------ статусы

def lesson_status(ls: dict, n: datetime) -> str:
    day = ls["date"]
    if dt_on(day, ls["end"]) <= n:
        return "done"
    if dt_on(day, ls["start"]) <= n:
        return "now"
    return "next"


def lesson_block_html(ls: dict, status: str | None = None) -> str:
    mark = {"done": "✅", "now": "🔴", "next": "⏳"}.get(status or "", "")
    head = f"{ls['start']}–{ls['end']} — {ls['pair_no']} пара"
    if ls.get("lesson_type"):
        head += f" | {ls['lesson_type']}"
    head = f"{mark} <b>{esc(head)}</b>" if mark else f"<b>{esc(head)}</b>"
    lines = [head, f"{ls.get('emoji') or '📚'} <b>{esc(ls['discipline'])}</b>"]
    tail = []
    if ls.get("teacher"):
        tail.append(esc(ls["teacher"]))
    if ls.get("room"):
        tail.append(f"ауд. {esc(ls['room'])}")
    if tail:
        lines.append(" • ".join(tail))
    return "\n".join(lines)


def day_header_html(day_iso: str) -> str:
    d = date.fromisoformat(day_iso)
    return f"📅 <b>{WEEKDAYS_FULL[d.weekday()]}, {fmt_dmy(d)}</b>"


def day_view_html(day_iso: str, n: datetime, with_statuses: bool) -> str:
    lessons = db.day_lessons(day_iso)
    if not lessons:
        return ""
    blocks = []
    for ls in lessons:
        st = lesson_status(ls, n) if with_statuses else None
        blocks.append(lesson_block_html(ls, st))
    out = day_header_html(day_iso) + "\n\n" + "\n\n".join(blocks)
    if with_statuses:
        out += "\n\n<b>Обозначения:</b> ✅ прошла • 🔴 идёт сейчас • ⏳ скоро начнётся"
    return out


def main_status_html(n: datetime | None = None) -> str:
    n = n or now()
    day = iso(n.date())
    lessons = db.day_lessons(day)
    if not lessons:
        return "📅 Сегодня пар нет."
    first, last = lessons[0], lessons[-1]
    first_dt, last_dt = dt_on(day, first["start"]), dt_on(day, last["end"])

    def brief(ls: dict) -> str:
        s = f"{ls['pair_no']} пара • {ls['discipline']}"
        if ls.get("lesson_type"):
            s += f" ({ls['lesson_type']})"
        if ls.get("room"):
            s += f", ауд. {ls['room']}"
        return esc(s)

    if n < first_dt:
        mins = int((first_dt - n).total_seconds() // 60)
        return f"⏳ Через {hm_ru(mins)} — {brief(first)}. Начало в {first['start']}."
    if n >= last_dt:
        return "🌙 На сегодня пар больше нет."
    for i, ls in enumerate(lessons):
        st, en = dt_on(day, ls["start"]), dt_on(day, ls["end"])
        if st <= n < en:
            left = int((en - n).total_seconds() // 60)
            return f"🔴 Сейчас идёт {brief(ls)} • до {ls['end']} (осталось {hm_ru(left)})."
        if n >= en and i + 1 < len(lessons) and n < dt_on(day, lessons[i + 1]["start"]):
            nxt = lessons[i + 1]
            return f"☕ Перемена • далее {brief(nxt)} в {nxt['start']}."
    return "🌙 На сегодня пар больше нет."


# ------------------------------------------------------------------ выбор дат сдачи

def next_lesson_options(disc_id: int, limit: int = 6) -> list[dict]:
    rows = db.q(
        "SELECT date, lesson_type, start FROM schedule WHERE discipline_id=? AND date>=?"
        " ORDER BY date, start",
        (disc_id, iso(today())),
    )
    seen: set[tuple] = set()
    out = []
    for r in rows:
        key = (r["date"], r["lesson_type"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": r["date"], "type": r["lesson_type"]})
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ импорт JSON

def import_schedule_json(text: str) -> dict:
    """Импорт расписания из JSON формата format_version=1. Возвращает отчёт."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Некорректный JSON: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("weeks"), list):
        raise ValueError("Ожидается объект с массивом «weeks»")
    warnings: list[str] = []
    per_day: dict[str, list[dict]] = {}
    n_weeks = 0
    for w in data["weeks"]:
        lessons = w.get("lessons") or []
        if not lessons:
            continue
        n_weeks += 1
        for l in lessons:
            try:
                day = date.fromisoformat(str(l["date"])).isoformat()
                start, end = str(l["start"])[:5], str(l["end"])[:5]
                parse_hm(start), parse_hm(end)
                name = str(l["discipline"]).strip()
            except Exception:
                warnings.append(f"Пропущена некорректная запись: {json.dumps(l, ensure_ascii=False)[:120]}")
                continue
            if not name:
                warnings.append(f"Запись без дисциплины {day} — пропущена")
                continue
            alias = DISCIPLINE_ALIASES.get(db.norm_name(name))
            disc = db.discipline_by_name(alias or name)
            if disc is None:
                did = db.ensure_discipline(alias or name)
                warnings.append(f"Создана новая дисциплина: «{alias or name}»")
            else:
                did = disc["id"]
            lt = l.get("lesson_type")
            if lt not in ("ПР", "ЛЕК", "ЛАБ", None, ""):
                warnings.append(f"Неизвестный тип занятия «{lt}» ({day}) — сохранён как есть")
            per_day.setdefault(day, []).append(
                {
                    "start": start,
                    "end": end,
                    "discipline_id": did,
                    "lesson_type": lt or None,
                    "room": (str(l["room"]).strip() if l.get("room") else None),
                }
            )
    for day, items in per_day.items():
        items.sort(key=lambda x: x["start"])
        rows = []
        for idx, it in enumerate(items):
            pair_no = None
            for i, (s, _) in enumerate(PAIR_TIMES, 1):
                if s == it["start"]:
                    pair_no = i
                    break
            rows.append(
                (
                    pair_no or idx + 1,
                    it["start"],
                    it["end"],
                    it["discipline_id"],
                    it["lesson_type"],
                    it["room"],
                )
            )
        db.replace_day(day, rows)
    if data.get("warnings"):
        warnings.extend(str(x) for x in data["warnings"])
    return {
        "weeks": n_weeks,
        "days": len(per_day),
        "lessons": sum(len(v) for v in per_day.values()),
        "day_list": sorted(per_day),
        "warnings": warnings,
    }
