"""API-тест через ASGI-транспорт httpx: auth (debug), me, today, homework, grades, admin."""
import os
import tempfile

tmp = tempfile.mkdtemp(prefix="r261api_")
os.environ["DATA_DIR"] = tmp
os.environ["DB_PATH"] = os.path.join(tmp, "bot.db")
os.environ["BOT_TOKEN"] = "123456:TESTTOKEN"
os.environ["ADMIN_IDS"] = "11111111"
os.environ["WEBAPP_DEBUG_FIO"] = "Аносов Владимир Сергеевич"

import json  # noqa: E402

import httpx  # noqa: E402

from bot import db  # noqa: E402
from bot.api import app, make_token  # noqa: E402
from bot.services import schedule_utils as su  # noqa: E402

db.init()
db.link_tg(db.student_by_fio("Аносов Владимир Сергеевич")["id"], 11111111)
su.import_schedule_json(__import__("json").dumps({"weeks": [{"lessons": [
    {"date": su.iso(su.today()), "start": "08:30", "end": "10:00", "discipline": "Математика", "lesson_type": "ПР", "room": "417"},
]}]}, ensure_ascii=False))
su.import_schedule_json(json.dumps({
    "weeks": [{"lessons": [
        {"date": "2026-10-23", "start": "08:30", "end": "10:00", "discipline": "Математика", "lesson_type": "ПР", "room": "417"},
    ]}]
}, ensure_ascii=False))
did = db.discipline_by_name("Математика")["id"]
db.create_hw(did, "Тест", "Задание", None, None, None, [], su.ts(), None)
db.create_textbook(did, "Учебник математики", "10–11 класс", [{"type": "document", "name": "a.pdf", "file_id": "X"}])
db.replace_discipline_grades(did, [(db.student_by_fio("Аносов Владимир Сергеевич")["id"], "2026-10-01", "5"),
                                   (db.student_by_fio("Аносов Владимир Сергеевич")["id"], "2026-10-02", "Н")])

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK  {name}")
    else:
        fail += 1
        print(f"FAIL  {name} {extra}")


async def main():
    global token
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/auth", json={"init_data": ""})
        check("auth debug", r.status_code == 200, r.text)
        token = r.json()["token"]
        check("is_admin из ADMIN_IDS", r.json()["is_admin"] is True)
        h = {"Authorization": "Bearer " + token}

        r = await c.get("/api/me", headers=h)
        check("/api/me", r.status_code == 200 and r.json()["fio"].startswith("Аносов"), r.text[:200])
        check("me.group Р 26-1", r.json()["group"] == "Р 26-1")
        check("me.settings default 30/19:00", r.json()["settings"]["next_pair_min"] == 30 and r.json()["settings"]["tomorrow_time"] == "19:00")
        check("me.semester есть", isinstance(r.json().get("semester"), dict) and "week" in r.json()["semester"], r.text[:150])
        check("settings.quiet есть", isinstance(r.json()["settings"].get("quiet"), bool))

        r = await c.get("/api/today", headers=h)
        check("/api/today", r.status_code == 200 and "status_text" in r.json())

        r = await c.post("/api/admin/day-notice", json={"date": "2026-11-03", "text": "3-ю пару отменили"}, headers=h)
        check("day-notice сохранён", r.status_code == 200, r.text[:100])
        r = await c.get("/api/schedule/day/2026-11-03", headers=h)
        check("day-notice в дне", r.json().get("day_notice") == "3-ю пару отменили", r.text[:150])
        r = await c.get(f"/api/schedule/next/{did}?all=1", headers=h)
        check("/api/schedule/next?all", r.status_code == 200 and isinstance(r.json()["lessons"], list), r.text[:120])
        r = await c.get("/api/schedule/weeks", headers=h)
        check("/api/schedule/weeks", r.status_code == 200 and len(r.json()["weeks"]) >= 1)
        wn = r.json()["weeks"][0]["n"]
        r = await c.get(f"/api/schedule/week/{wn}", headers=h)
        check("/api/schedule/week", r.status_code == 200 and len(r.json()["days"]) == 7)

        r = await c.get("/api/homework", headers=h)
        check("/api/homework groups", r.status_code == 200 and r.json()["groups"][0]["discipline"]["name"] == "Математика")
        hid = r.json()["groups"][0]["items"][0]["id"]
        check("hw.task отдаётся", r.json()["groups"][0]["items"][0].get("task") == "Задание", r.text[:150])
        check("hw.new = True до просмотра", r.json()["groups"][0]["items"][0]["new"] is True)
        r = await c.get(f"/api/homework/{hid}", headers=h)
        check("/api/homework/{id}", r.status_code == 200)
        r = await c.get("/api/homework", headers=h)
        check("hw.new = False после просмотра", r.json()["groups"][0]["items"][0]["new"] is False)
        r = await c.post(f"/api/homework/{hid}/done", json={"done": True}, headers=h)
        check("hw done", r.json()["done"] is True)

        r = await c.get("/api/textbooks", headers=h)
        check("/api/textbooks", r.status_code == 200 and r.json()["groups"][0]["items"][0]["title"].startswith("Учебник"))

        r = await c.get("/api/grades", headers=h)
        g = r.json()
        check("/api/grades avg=5", g["avg"] == 5.0, g.get("avg"))
        check("/api/grades counts.h=1", g["counts"]["h"] == 1)
        check("все 15 дисциплин присутствуют", len(g["disciplines"]) == 15)

        r = await c.post("/api/settings", json={"next_pair_min": 45, "theme": "light", "tomorrow_time": "18:30"}, headers=h)
        check("/api/settings", r.status_code == 200 and r.json()["theme"] == "light")
        r = await c.get("/api/me", headers=h)
        check("настройки применились", r.json()["settings"]["next_pair_min"] == 45 and r.json()["settings"]["tomorrow_time"] == "18:30")

        r = await c.get("/api/attendance/today", headers=h)
        check("/api/attendance/today", r.status_code == 200 and "active" in r.json())
        r = await c.post("/api/attendance/reset", headers=h)
        check("/api/attendance/reset", r.status_code == 200, r.text[:100])

        r = await c.get("/api/admin/stats", headers=h)
        check("/api/admin/stats", r.status_code == 200 and r.json()["students_total"] == 25, r.text[:200])
        r = await c.get("/api/admin/students", headers=h)
        check("/api/admin/students", r.status_code == 200 and len(r.json()) == 25)
        r = await c.get("/api/admin/homework", headers=h)
        check("/api/admin/homework", r.status_code == 200 and len(r.json()["groups"]) == 1)
        r = await c.get(f"/api/admin/next-lessons/{did}", headers=h)
        check("/api/admin/next-lessons", r.status_code == 200 and isinstance(r.json(), list))
        r = await c.put("/api/admin/schedule/day/2026-11-02", json={"lessons": [
            {"pair_no": 1, "start": "08:30", "end": "10:00", "discipline_id": did, "lesson_type": "ЛЕК", "room": "415"}
        ]}, headers=h)
        check("PUT schedule day", r.status_code == 200)
        r = await c.get("/api/schedule/day/2026-11-02", headers=h)
        check("день сохранился", r.json()["lessons"][0]["room"] == "415")
        r = await c.delete("/api/admin/schedule/day/2026-11-02", headers=h)
        check("DELETE schedule day", r.status_code == 200)
        r = await c.get("/api/admin/schedule/day/2026-11-02", headers=h)
        check("день удалён", r.json()["lessons"] == [])

        r = await c.post("/api/admin/attendance/ask", json={"mode": "day"}, headers=h)
        check("admin ask day", r.status_code == 200 and "sent" in r.json(), r.text[:100])
        r = await c.post("/api/admin/attendance/ask", json={"mode": "pair", "pair_no": 1}, headers=h)
        check("admin ask pair", r.status_code == 200, r.text[:150])
        r = await c.post("/api/admin/day-notice", json={"date": "2026-11-04", "text": "Первая метка"}, headers=h)
        check("метка 1", r.status_code == 200)
        r = await c.post("/api/admin/day-notice", json={"date": "2026-11-05", "text": "Вторая метка"}, headers=h)
        check("метка 2 (баг 500)", r.status_code == 200, r.text[:150])
        r = await c.post("/api/admin/day-notice", json={"date": "2026-11-04", "text": "Повтор той же даты"}, headers=h)
        check("метка повторно", r.status_code == 200, r.text[:150])
        r = await c.delete("/api/admin/day-notice/2026-11-04", headers=h)
        r = await c.delete("/api/admin/day-notice/2026-11-05", headers=h)
        r = await c.post("/api/admin/grades/sync", headers=h)
        check("sync без настроек → ok False с ошибкой", r.status_code == 200 and r.json()["ok"] is False)

        r = await c.get("/api/attendance/week-summary", headers=h)
        check("week-summary для стаффа", r.status_code == 200 and "days" in r.json(), r.text[:120])
        r = await c.get("/api/rating", headers=h)
        rt = r.json()
        check("/api/rating avg", r.status_code == 200 and rt["items"][0]["pos"] == 1 and "short" in rt["items"][0], r.text[:150])
        r = await c.get("/api/rating?sort=skips", headers=h)
        check("/api/rating skips", r.status_code == 200)
        r = await c.get("/api/rating?sort=late", headers=h)
        check("/api/rating late", r.status_code == 200)
        r = await c.post("/api/admin/maintenance", json={"on": True, "until": "01.01.2030 00:00"}, headers=h)
        check("тех.работы вкл", r.status_code == 200, r.text[:100])
        st2 = db.all_students()[1]
        db.link_tg(st2["id"], 222222222)
        anon_headers = {"Authorization": "Bearer " + make_token(222222222)}
        r = await c.get("/api/today", headers=anon_headers)
        check("не-админ при тех.работах -> 503", r.status_code == 503, r.status_code)
        r = await c.get("/api/today", headers=h)
        check("админ при тех.работах работает", r.status_code == 200, r.status_code)
        r = await c.get("/api/admin/day-notices", headers=h)
        check("day-notices список", r.status_code == 200 and any(x["date"] == "2026-11-03" for x in r.json()["items"]), r.text[:150])
        r = await c.delete("/api/admin/day-notice/2026-11-03", headers=h)
        check("day-notice удаление", r.status_code == 200)
        r = await c.get("/api/schedule/day/2026-11-03", headers=h)
        check("day-notice снят", r.json().get("day_notice") == "", r.text[:150])
        r = await c.post("/api/admin/maintenance", json={"on": False}, headers=h)
        check("тех.работы выкл", r.status_code == 200)
        r = await c.get("/api/today", headers=h)
        check("после выкл доступ вернулся", r.status_code == 200)
        r = await c.post("/api/admin/exam-week", json={"on": True}, headers=h)
        check("контрольная вкл", r.status_code == 200)
        r = await c.get("/api/grades", headers=h)
        g6 = r.json()
        check("exam_week в оценках", g6.get("exam_week") is True, r.text[:120])
        check("risk_ids список", isinstance(g6.get("risk_ids"), list))
        r = await c.post("/api/admin/exam-week", json={"on": False}, headers=h)
        r = await c.get("/api/admin/backup", headers=h)
        check("бэкап скачивается", r.status_code == 200 and r.headers["content-type"].startswith("application/octet-stream"))
        backup_bytes = r.content
        r = await c.post("/api/admin/restore", files={"file": ("b.db", backup_bytes, "application/octet-stream")}, headers=h)
        check("бэкап загружается обратно", r.status_code == 200, r.text[:150])
        r = await c.get("/api/me")
        check("без токена — 401", r.status_code == 401)

    print(f"\nИтого API: OK={ok}, FAIL={fail}")
    return fail


import asyncio  # noqa: E402

fails = asyncio.run(main())
import sys  # noqa: E402

sys.exit(1 if fails else 0)
