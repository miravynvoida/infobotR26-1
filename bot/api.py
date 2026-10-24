"""FastAPI: API мини-приложения + раздача статики webapp/."""
import asyncio
import hashlib
import hmac
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db
from .services import attendance as att_svc
from .services import schedule_utils as su
from .services.grades import sync_grades
from .services.tg_files import (
    hw_notice_html,
    send_files as tg_send_files,
    send_message_html,
    upload_get_file_id,
)

app = FastAPI(title="R26-1 API", docs_url=None, redoc_url=None, openapi_url=None)

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
TOKEN_TTL = 30 * 24 * 3600
SESSION_SECRET = hmac.new(b"r261-session", config.cfg.bot_token.encode(), hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ авторизация

def verify_init_data(raw: str) -> dict:
    try:
        params = dict(parse_qsl(raw, keep_blank_values=True))
        received = params.pop("hash", "")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret = hmac.new(b"WebAppData", config.cfg.bot_token.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated, received):
            raise ValueError
        auth_date = int(params.get("auth_date", "0"))
        if auth_date and time.time() - auth_date > TOKEN_TTL:
            raise ValueError("expired")
        return json.loads(params["user"])
    except Exception as e:
        raise HTTPException(401, f"initData не прошёл проверку: {e}") from e


def make_token(tg_id: int) -> str:
    exp = int(time.time()) + TOKEN_TTL
    sig = hmac.new(SESSION_SECRET.encode(), f"{tg_id}.{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{tg_id}.{exp}.{sig}"


def parse_token(token: str) -> int:
    try:
        tg_id, exp, sig = token.split(".")
        if int(exp) < time.time():
            raise ValueError
        calc = hmac.new(SESSION_SECRET.encode(), f"{tg_id}.{exp}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, sig):
            raise ValueError
        return int(tg_id)
    except Exception as e:
        raise HTTPException(401, "Неверный токен сессии") from e


class AuthBody(BaseModel):
    init_data: str = ""


@app.post("/api/auth")
async def api_auth(body: AuthBody):
    if body.init_data:
        user = verify_init_data(body.init_data)
        tg_id = user["id"]
    elif config.cfg.debug_fio:
        st = db.student_by_fio(config.cfg.debug_fio)
        if not st or not st["tg_id"]:
            raise HTTPException(400, "WEBAPP_DEBUG_FIO: студент не найден или не авторизован в боте")
        tg_id = st["tg_id"]
    else:
        raise HTTPException(401, "Нет initData")
    student = db.student_by_tg(tg_id)
    if student is None:
        raise HTTPException(403, "Вы не авторизованы в боте. Нажмите /start у бота.")
    return {
        "token": make_token(tg_id),
        "is_admin": tg_id in config.cfg.admin_ids,
        "is_staff": tg_id in config.cfg.staff_ids,
    }


def cur(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Нужен токен")
    tg_id = parse_token(auth[7:])
    student = db.student_by_tg(tg_id)
    if student is None:
        raise HTTPException(403, "Не авторизован")
    return {"tg_id": tg_id, "student": student}


def adm(user: dict = Depends(cur)) -> dict:
    if user["tg_id"] not in config.cfg.admin_ids:
        raise HTTPException(403, "Только для админов")
    return user


def staff(user: dict = Depends(cur)) -> dict:
    if user["tg_id"] not in config.cfg.staff_ids:
        raise HTTPException(403, "Только для старосты/замов/админов")
    return user


# ------------------------------------------------------------------ общее

def lesson_dict(ls: dict, n: datetime | None = None, with_status: bool = False) -> dict:
    out = {
        "pair_no": ls["pair_no"],
        "start": ls["start"],
        "end": ls["end"],
        "discipline_id": ls["discipline_id"],
        "discipline": ls["discipline"],
        "emoji": ls["emoji"],
        "teacher": ls["teacher"],
        "type": ls["lesson_type"],
        "room": ls["room"],
    }
    if with_status and n is not None:
        out["status"] = su.lesson_status(ls, n)
    return out


@app.get("/api/me")
def api_me(user: dict = Depends(cur)):
    st = user["student"]
    stats = db.student_stats(st["id"])
    s = db.get_settings(st["id"])
    return {
        "fio": st["fio"],
        "short": su.short_name(st["fio"]),
        "group": config.cfg.group_name,
        "streak": att_svc.streak(st["id"]),
        "specialty": config.cfg.specialty,
        "stats": {"avg": stats["avg"], "total": stats["total"], "h": stats["h"], "b": stats["b"], "o": stats["o"]},
        "settings": {
            "next_pair": bool(s["next_pair"]),
            "next_pair_min": s["next_pair_min"],
            "tomorrow": bool(s["tomorrow"]),
            "tomorrow_time": s["tomorrow_time"],
            "misc": bool(s["misc"]),
            "quiet": bool(s["quiet"]),
            "theme": s["theme"],
        },
        "is_admin": user["tg_id"] in config.cfg.admin_ids,
        "is_staff": user["tg_id"] in config.cfg.staff_ids,
    }


@app.get("/api/today")
def api_today(user: dict = Depends(cur)):
    n = su.now()
    day = su.iso(n.date())
    lessons = db.day_lessons(day)
    return {
        "date": day,
        "weekday": su.WEEKDAYS_FULL[n.weekday()],
        "week_number": su.study_week(n.date()),
        "status_text": su.main_status_html(n),
        "day_notice": day_notice(day),
        "lessons": [lesson_dict(ls, n, True) for ls in lessons],
    }


@app.get("/api/schedule/weeks")
def api_weeks(user: dict = Depends(cur)):
    return {"weeks": su.available_weeks()}


@app.get("/api/schedule/week/{n}")
def api_schedule_week(n: int, user: dict = Depends(cur)):
    try:
        start, end = su.week_bounds(n)
    except Exception:
        raise HTTPException(404, "Нет такой недели")
    days = []
    d = start
    while d <= end:
        lessons = db.day_lessons(d.isoformat())
        days.append(
            {
                "date": d.isoformat(),
                "weekday": su.WEEKDAYS_FULL[d.weekday()],
                "lessons": [lesson_dict(ls) for ls in lessons],
            }
        )
        d += timedelta(days=1)
    return {"week_number": n, "start": start.isoformat(), "end": end.isoformat(), "days": days}


@app.get("/api/schedule/day/{day_iso}")
def api_schedule_day(day_iso: str, user: dict = Depends(cur)):
    try:
        d = date.fromisoformat(day_iso)
    except ValueError:
        raise HTTPException(400, "Неверная дата")
    n = su.now()
    today = d == n.date()
    lessons = db.day_lessons(day_iso)
    return {
        "date": day_iso,
        "weekday": su.WEEKDAYS_FULL[d.weekday()],
        "day_notice": day_notice(day_iso),
        "lessons": [lesson_dict(ls, n, today) for ls in lessons],
    }


@app.get("/api/schedule/next/{disc_id}")
def api_next_lesson(disc_id: int, all: bool = False, user: dict = Depends(cur)):
    disc = db.discipline_by_id(disc_id)
    if disc is None:
        raise HTTPException(404, "Дисциплина не найдена")
    n = su.now()
    today_iso = su.iso(n.date())
    rows = db.q(
        "SELECT s.*, d.name AS discipline, d.emoji, d.teacher FROM schedule s "
        "JOIN disciplines d ON d.id = s.discipline_id WHERE s.discipline_id=? AND s.date>=? "
        "ORDER BY s.date, s.start",
        (disc_id, today_iso),
    )
    # на сегодня оставляем только незаконченные пары
    rows = [r for r in rows if r["date"] > today_iso or su.lesson_status(r, n) != "done"]

    if all:
        out = []
        for r in rows:
            out.append(
                {
                    "date": r["date"],
                    "weekday": su.WEEKDAYS_FULL[date.fromisoformat(r["date"]).weekday()],
                    "lesson": lesson_dict(r),
                }
            )
        return {"discipline": disc["name"], "emoji": disc["emoji"], "lessons": out}

    if not rows:
        return {"discipline": disc["name"], "emoji": disc["emoji"], "lesson": None, "lessons": []}
    first = rows[0]
    return {
        "discipline": disc["name"],
        "emoji": disc["emoji"],
        "lesson": lesson_dict(first),
        "date": first["date"],
        "weekday": su.WEEKDAYS_FULL[date.fromisoformat(first["date"]).weekday()],
        "lessons": [],
    }


# ------------------------------------------------------------------ дз

def hw_dict(h: dict, unviewed: set[int], done: set[int]) -> dict:
    files = json.loads(h.get("files") or "[]")
    return {
        "id": h["id"],
        "discipline": {"id": h["discipline_id"], "name": h["discipline"], "emoji": h["emoji"]},
        "title": h["title"],
        "task": h["task_text"],
        "due_date": h["due_date"],
        "due_type": h.get("due_type"),
        "published_at": h.get("published_at"),
        "explanation": h.get("explanation"),
        "files": [{"name": f.get("name"), "type": f.get("type")} for f in files],
        "has_files": bool(files),
        "new": h["id"] in unviewed,
        "done": h["id"] in done,
    }


@app.get("/api/homework")
def api_homework(user: dict = Depends(cur)):
    sid = user["student"]["id"]
    unviewed = db.unviewed_hw_ids(sid)
    done = db.done_hw_ids(sid)
    groups: dict[int, dict] = {}
    for h in db.active_homework():
        g = groups.setdefault(
            h["discipline_id"],
            {"discipline": {"id": h["discipline_id"], "name": h["discipline"], "emoji": h["emoji"]}, "items": []},
        )
        g["items"].append(hw_dict(h, unviewed, done))
    return {"groups": list(groups.values()), "total_new": len(unviewed)}


@app.get("/api/homework/{hid}")
def api_homework_one(hid: int, user: dict = Depends(cur)):
    h = db.hw_by_id(hid)
    if h is None or h["archived"]:
        raise HTTPException(404, "Задание не найдено")
    sid = user["student"]["id"]
    db.mark_viewed(sid, hid, su.ts())
    return hw_dict(h, db.unviewed_hw_ids(sid), db.done_hw_ids(sid))


class DoneBody(BaseModel):
    done: bool


@app.post("/api/homework/{hid}/done")
def api_homework_done(hid: int, body: DoneBody, user: dict = Depends(cur)):
    if db.hw_by_id(hid) is None:
        raise HTTPException(404, "Задание не найдено")
    db.set_hw_done(user["student"]["id"], hid, body.done, su.ts())
    return {"done": body.done}


@app.post("/api/homework/{hid}/send")
async def api_homework_send(hid: int, user: dict = Depends(cur)):
    h = db.hw_by_id(hid)
    if h is None:
        raise HTTPException(404, "Задание не найдено")
    files = json.loads(h.get("files") or "[]")
    sent = await tg_send_files(user["tg_id"], files)
    return {"sent": sent, "total": len(files)}


# ------------------------------------------------------------------ учебники

@app.get("/api/textbooks")
def api_textbooks(user: dict = Depends(cur)):
    groups: dict[int, dict] = {}
    for t in db.all_textbooks():
        g = groups.setdefault(
            t["discipline_id"],
            {"discipline": {"id": t["discipline_id"], "name": t["discipline"], "emoji": t["emoji"]}, "items": []},
        )
        g["items"].append(
            {
                "id": t["id"],
                "title": t["title"],
                "description": t.get("description"),
                "files": [{"name": f.get("name"), "type": f.get("type")} for f in json.loads(t.get("files") or "[]")],
            }
        )
    return {"groups": list(groups.values())}


@app.post("/api/textbooks/{tid}/send")
async def api_textbook_send(tid: int, user: dict = Depends(cur)):
    t = db.textbook_by_id(tid)
    if t is None:
        raise HTTPException(404, "Не найдено")
    files = json.loads(t.get("files") or "[]")
    sent = await tg_send_files(user["tg_id"], files)
    return {"sent": sent, "total": len(files)}


# ------------------------------------------------------------------ оценки

@app.get("/api/grades")
def api_grades(user: dict = Depends(cur)):
    sid = user["student"]["id"]
    stats = db.student_stats(sid)
    rows = db.student_grades(sid)
    by_disc: dict[int, dict] = {}
    for d in db.all_disciplines():
        by_disc[d["id"]] = {"id": d["id"], "name": d["name"], "emoji": d["emoji"], "grades": []}
    for r in rows:
        by_disc[r["discipline_id"]]["grades"].append({"date": r["date"], "value": r["value"]})
    for disc in by_disc.values():
        nums = [int(g["value"]) for g in disc["grades"] if g["value"] in ("2", "3", "4", "5")]
        disc["avg"] = round(sum(nums) / len(nums), 2) if nums else None
    months: dict[str, list[int]] = {}
    for disc in by_disc.values():
        for gr in disc["grades"]:
            if gr["value"] in ("2", "3", "4", "5") and gr["date"]:
                months.setdefault(gr["date"][:7], []).append(int(gr["value"]))
    MONTHS_RU = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
    trend = []
    for m in sorted(months):
        vals = months[m]
        trend.append({
            "label": MONTHS_RU[int(m[5:7]) - 1],
            "avg": round(sum(vals) / len(vals), 2),
            "n": len(vals),
        })
    all_marks = [int(r["value"]) for r in db.q(
        "SELECT value FROM grades WHERE value IN ('2','3','4','5')"
    )]
    group_avg = round(sum(all_marks) / len(all_marks), 2) if all_marks else None
    return {
        "avg": stats["avg"],
        "total": stats["total"],
        "counts": {"h": stats["h"], "b": stats["b"], "o": stats["o"]},
        "disciplines": list(by_disc.values()),
        "trend": trend,
        "group_avg": group_avg,
    }


# ------------------------------------------------------------------ настройки

class SettingsBody(BaseModel):
    next_pair: bool | None = None
    next_pair_min: int | None = None
    tomorrow: bool | None = None
    tomorrow_time: str | None = None
    misc: bool | None = None
    theme: str | None = None
    quiet: bool | None = None


@app.post("/api/settings")
def api_settings(body: SettingsBody, user: dict = Depends(cur)):
    sid = user["student"]["id"]
    fields = {}
    if body.next_pair is not None:
        fields["next_pair"] = int(body.next_pair)
    if body.next_pair_min is not None and body.next_pair_min in (5, 10, 15, 30, 45, 60, 90):
        fields["next_pair_min"] = body.next_pair_min
    if body.tomorrow is not None:
        fields["tomorrow"] = int(body.tomorrow)
    if body.tomorrow_time and su.parse_hm(body.tomorrow_time):
        fields["tomorrow_time"] = body.tomorrow_time
    if body.misc is not None:
        fields["misc"] = int(body.misc)
    if body.theme in ("dark", "light"):
        fields["theme"] = body.theme
    if body.quiet is not None:
        fields["quiet"] = int(body.quiet)
    if fields:
        db.update_settings(sid, **fields)
    s = db.get_settings(sid)
    return {"ok": True, "theme": s["theme"]}


# ------------------------------------------------------------------ посещаемость

@app.get("/api/attendance/today")
def api_attendance_today(user: dict = Depends(cur)):
    active = att_svc.ask_active()
    if active is None:
        return {"active": False, "lessons": []}
    resp = db.get_attendance(active["date"], user["student"]["id"])
    return {
        "active": True,
        "date": active["date"],
        "first_start": active["first_start"],
        "response": (
            {"status": resp["status"], "missing_pairs": json.loads(resp["missing_pairs"] or "[]")} if resp else None
        ),
        "lessons": [
            {"pair_no": ls["pair_no"], "start": ls["start"], "discipline": ls["discipline"], "emoji": ls["emoji"]}
            for ls in active["lessons"]
        ],
    }


class AttBody(BaseModel):
    status: str
    missing_pairs: list[int] = []


@app.post("/api/attendance")
def api_attendance(body: AttBody, user: dict = Depends(cur)):
    if body.status not in ("full", "none", "partial", "sick"):
        raise HTTPException(400, "Неверный статус")
    day = su.iso(su.today())
    lessons = db.day_lessons(day)
    if not lessons:
        raise HTTPException(400, "Сегодня пар нет")
    missing = [p for p in body.missing_pairs if any(ls["pair_no"] == p for ls in lessons)] if body.status == "partial" else []
    db.set_attendance(day, user["student"]["id"], body.status, missing, su.ts())
    return {"ok": True}


@app.get("/api/attendance/summary")
def api_attendance_summary(user: dict = Depends(staff)):
    return att_svc.summary(su.iso(su.today()))


@app.get("/api/attendance/week-summary")
def api_attendance_week_summary(user: dict = Depends(staff)):
    return {"days": att_svc.week_summary()}


class DayNoticeBody(BaseModel):
    date: str
    text: str  # "" — убрать метку


@app.post("/api/admin/day-notice")
def api_admin_day_notice(body: DayNoticeBody, user: dict = Depends(adm)):
    try:
        date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(400, "Неверная дата")
    db.kv_set(f"day_notice_{body.date}", body.text.strip())
    return {"ok": True}


def day_notice(day_iso: str) -> str:
    return db.kv_get(f"day_notice_{day_iso}", "")


# ------------------------------------------------------------------ админ: статистика

@app.get("/api/admin/stats")
def api_admin_stats(user: dict = Depends(adm)):
    students = db.all_students()
    authed = [s for s in students if s["tg_id"]]
    day = su.iso(su.today())
    return {
        "students_total": len(students),
        "students_auth": len(authed),
        "disciplines": len(db.all_disciplines()),
        "schedule_days": len(db.schedule_dates()),
        "hw_active": len(db.active_homework()),
        "hw_archived": len(db.archived_homework()),
        "textbooks": len(db.all_textbooks()),
        "last_grades_sync": db.kv_get("last_grades_sync") or None,
        "attendance_today": {"answered": len(db.day_attendance(day)), "total": len(authed)},
    }


@app.post("/api/admin/grades/sync")
async def api_admin_sync(user: dict = Depends(adm)):
    report = await asyncio.to_thread(sync_grades)
    return report


# ------------------------------------------------------------------ админ: студенты

@app.get("/api/admin/students")
def api_admin_students(user: dict = Depends(adm)):
    return [
        {
            "id": s["id"], "fio": s["fio"], "code": s["code"], "authorized": bool(s["tg_id"]),
            "tg_id": s["tg_id"], "authorized_at": s["authorized_at"],
        }
        for s in db.all_students()
    ]


class StudentBody(BaseModel):
    fio: str


@app.post("/api/admin/students")
def api_admin_student_add(body: StudentBody, user: dict = Depends(adm)):
    if db.student_by_fio(body.fio):
        raise HTTPException(400, "Такой студент уже есть")
    st = db.add_student(body.fio)
    return {"id": st["id"], "fio": st["fio"], "code": st["code"]}


class StudentPatch(BaseModel):
    action: str  # regen | unlink


@app.patch("/api/admin/students/{sid}")
def api_admin_student_patch(sid: int, body: StudentPatch, user: dict = Depends(adm)):
    if db.student_by_id(sid) is None:
        raise HTTPException(404, "Не найден")
    if body.action == "regen":
        return {"code": db.regen_code(sid)}
    if body.action == "unlink":
        db.unlink_tg(sid)
        return {"ok": True}
    raise HTTPException(400, "Неизвестное действие")


@app.delete("/api/admin/students/{sid}")
def api_admin_student_delete(sid: int, user: dict = Depends(adm)):
    if db.student_by_id(sid) is None:
        raise HTTPException(404, "Не найден")
    db.delete_student(sid)
    return {"ok": True}


# ------------------------------------------------------------------ админ: дисциплины

@app.get("/api/admin/disciplines")
def api_admin_disciplines(user: dict = Depends(adm)):
    hw = db.active_homework() + db.archived_homework()
    hw_discs = {h["discipline_id"] for h in hw}
    tb_discs = {t["discipline_id"] for t in db.all_textbooks()}
    return [
        {
            "id": d["id"], "name": d["name"], "emoji": d["emoji"], "teacher": d["teacher"],
            "has_hw": d["id"] in hw_discs, "has_textbooks": d["id"] in tb_discs,
        }
        for d in db.all_disciplines()
    ]


class DiscBody(BaseModel):
    name: str
    emoji: str | None = None
    teacher: str | None = None


@app.post("/api/admin/disciplines")
def api_admin_disc_add(body: DiscBody, user: dict = Depends(adm)):
    if db.discipline_by_name(body.name):
        raise HTTPException(400, "Уже есть такая дисциплина")
    did = db.ensure_discipline(body.name, body.emoji or "📚", body.teacher)
    return {"id": did}


class DiscPatch(BaseModel):
    name: str | None = None
    emoji: str | None = None
    teacher: str | None = None


@app.patch("/api/admin/disciplines/{did}")
def api_admin_disc_patch(did: int, body: DiscPatch, user: dict = Depends(adm)):
    d = db.discipline_by_id(did)
    if d is None:
        raise HTTPException(404, "Не найдена")
    if body.name:
        db.ex("UPDATE disciplines SET name=?, name_norm=? WHERE id=?", (body.name, db.norm_name(body.name), did))
    if body.emoji is not None:
        db.ex("UPDATE disciplines SET emoji=? WHERE id=?", (body.emoji[:4] or "📚", did))
    if body.teacher is not None:
        db.ex("UPDATE disciplines SET teacher=? WHERE id=?", (body.teacher or None, did))
    return {"ok": True}


@app.delete("/api/admin/disciplines/{did}")
def api_admin_disc_delete(did: int, user: dict = Depends(adm)):
    usage = db.discipline_usage(did)
    if sum(usage.values()):
        raise HTTPException(400, f"Дисциплина используется: {usage}")
    db.ex("DELETE FROM disciplines WHERE id=?", (did,))
    return {"ok": True}


# ------------------------------------------------------------------ админ: дз

@app.get("/api/admin/homework")
def api_admin_hw(archived: int = 0, user: dict = Depends(adm)):
    groups: dict[int, dict] = {}
    for h in db.homework_by_discipline(archived):
        g = groups.setdefault(
            h["discipline_id"],
            {"discipline": {"id": h["discipline_id"], "name": h["discipline"], "emoji": h["emoji"]}, "items": []},
        )
        g["items"].append(
            {
                "id": h["id"], "title": h["title"], "task": h["task_text"], "due_date": h["due_date"],
                "due_type": h.get("due_type"), "published_at": h.get("published_at"),
                "explanation": h.get("explanation"),
                "files": json.loads(h.get("files") or "[]"), "archived": bool(h["archived"]),
            }
        )
    return {"groups": list(groups.values())}


class HwBody(BaseModel):
    discipline_id: int
    title: str
    task: str
    due_date: str | None = None
    due_type: str | None = None
    explanation: str | None = None
    files: list[dict] = []
    published_at: str | None = None


@app.post("/api/admin/homework")
async def api_admin_hw_create(body: HwBody, user: dict = Depends(adm)):
    if db.discipline_by_id(body.discipline_id) is None:
        raise HTTPException(400, "Нет такой дисциплины")
    hid = db.create_hw(
        body.discipline_id, body.title, body.task, body.due_date, body.due_type,
        body.explanation, body.files, body.published_at or su.ts(), user["student"]["id"],
    )
    h = db.hw_by_id(hid)
    sent = 0
    for st in db.authorized_students():
        try:
            await send_message_html(
                st["tg_id"],
                hw_notice_html(h, {"name": h["discipline"], "emoji": h["emoji"]}),
                [[{"text": "Открыть", "callback_data": f"hw:v:{hid}"}]],
            )
            sent += 1
        except Exception:
            continue
    return {"id": hid, "sent": sent}


class HwPatch(BaseModel):
    title: str | None = None
    task: str | None = None
    due_date: str | None = None
    due_type: str | None = None
    published_at: str | None = None
    explanation: str | None = None
    discipline_id: int | None = None
    files: list[dict] | None = None
    archived: bool | None = None


@app.patch("/api/admin/homework/{hid}")
def api_admin_hw_patch(hid: int, body: HwPatch, user: dict = Depends(adm)):
    if db.hw_by_id(hid) is None:
        raise HTTPException(404, "Не найдено")
    fields = {}
    for k in ("title", "task_text", "due_date", "due_type", "published_at", "explanation", "discipline_id"):
        v = getattr(body, "task" if k == "task_text" else k)
        if v is not None:
            fields[k] = v
    if body.files is not None:
        fields["files"] = body.files
    if fields:
        db.update_hw(hid, **fields)
    if body.archived is not None:
        db.set_hw_archived(hid, body.archived, su.ts() if body.archived else None)
    return {"ok": True}


@app.delete("/api/admin/homework/{hid}")
def api_admin_hw_delete(hid: int, user: dict = Depends(adm)):
    if db.hw_by_id(hid) is None:
        raise HTTPException(404, "Не найдено")
    db.delete_hw(hid)
    return {"ok": True}


@app.get("/api/admin/next-lessons/{disc_id}")
def api_admin_next_lessons(disc_id: int, user: dict = Depends(adm)):
    return su.next_lesson_options(disc_id, limit=6)


# ------------------------------------------------------------------ админ: учебники

@app.get("/api/admin/textbooks")
def api_admin_tb(user: dict = Depends(adm)):
    groups: dict[int, dict] = {}
    for t in db.all_textbooks():
        g = groups.setdefault(
            t["discipline_id"],
            {"discipline": {"id": t["discipline_id"], "name": t["discipline"], "emoji": t["emoji"]}, "items": []},
        )
        g["items"].append(
            {"id": t["id"], "title": t["title"], "description": t.get("description"), "files": json.loads(t.get("files") or "[]")}
        )
    return {"groups": list(groups.values())}


class TbBody(BaseModel):
    discipline_id: int
    title: str
    description: str | None = None
    files: list[dict] = []


@app.post("/api/admin/textbooks")
def api_admin_tb_create(body: TbBody, user: dict = Depends(adm)):
    if db.discipline_by_id(body.discipline_id) is None:
        raise HTTPException(400, "Нет такой дисциплины")
    tid = db.create_textbook(body.discipline_id, body.title, body.description, body.files)
    return {"id": tid}


class TbPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    files: list[dict] | None = None


@app.patch("/api/admin/textbooks/{tid}")
def api_admin_tb_patch(tid: int, body: TbPatch, user: dict = Depends(adm)):
    if db.textbook_by_id(tid) is None:
        raise HTTPException(404, "Не найдено")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if fields:
        db.update_textbook(tid, **fields)
    return {"ok": True}


@app.delete("/api/admin/textbooks/{tid}")
def api_admin_tb_delete(tid: int, user: dict = Depends(adm)):
    if db.textbook_by_id(tid) is None:
        raise HTTPException(404, "Не найдено")
    db.delete_textbook(tid)
    return {"ok": True}


# ------------------------------------------------------------------ админ: расписание

@app.get("/api/admin/schedule/day/{day_iso}")
def api_admin_schedule_day(day_iso: str, user: dict = Depends(adm)):
    try:
        date.fromisoformat(day_iso)
    except ValueError:
        raise HTTPException(400, "Неверная дата")
    return {"date": day_iso, "lessons": [lesson_dict(ls) for ls in db.day_lessons(day_iso)]}


class LessonBody(BaseModel):
    pair_no: int
    start: str
    end: str
    discipline_id: int
    lesson_type: str | None = None
    room: str | None = None


class DayBody(BaseModel):
    lessons: list[LessonBody]


@app.put("/api/admin/schedule/day/{day_iso}")
def api_admin_schedule_put(day_iso: str, body: DayBody, user: dict = Depends(adm)):
    try:
        date.fromisoformat(day_iso)
    except ValueError:
        raise HTTPException(400, "Неверная дата")
    pairs = [l.pair_no for l in body.lessons]
    if len(pairs) != len(set(pairs)):
        raise HTTPException(400, "Дублируются номера пар")
    for l in body.lessons:
        if db.discipline_by_id(l.discipline_id) is None:
            raise HTTPException(400, f"Нет дисциплины {l.discipline_id}")
        if not su.parse_hm(l.start) or not su.parse_hm(l.end):
            raise HTTPException(400, "Неверное время")
    db.replace_day(
        day_iso,
        [(l.pair_no, l.start, l.end, l.discipline_id, l.lesson_type, l.room) for l in body.lessons],
    )
    return {"ok": True, "lessons": len(body.lessons)}


@app.delete("/api/admin/schedule/day/{day_iso}")
def api_admin_schedule_delete(day_iso: str, user: dict = Depends(adm)):
    db.delete_day(day_iso)
    return {"ok": True}


class ImportBody(BaseModel):
    json: str


@app.post("/api/admin/schedule/import")
def api_admin_schedule_import(body: ImportBody, user: dict = Depends(adm)):
    try:
        return su.import_schedule_json(body.json)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ админ: загрузка файлов и рассылка

@app.post("/api/admin/upload")
async def api_admin_upload(file: UploadFile = File(...), user: dict = Depends(adm)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Пустой файл")
    if len(content) > 45 * 1024 * 1024:
        raise HTTPException(400, "Файл больше 45 МБ")
    try:
        desc = await upload_get_file_id(user["tg_id"], file.filename or "file", content, file.content_type or "")
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return desc


class BroadcastBody(BaseModel):
    text: str


@app.post("/api/admin/broadcast")
async def api_admin_broadcast(body: BroadcastBody, user: dict = Depends(adm)):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "Пустой текст")
    sent = 0
    total = 0
    for st in db.authorized_students():
        total += 1
        try:
            await send_message_html(st["tg_id"], text)
            sent += 1
        except Exception:
            continue
    return {"sent": sent, "total": total}


# ------------------------------------------------------------------ статика (последним!)

app.mount("/", StaticFiles(directory=str(WEBAPP_DIR), html=True), name="webapp")
