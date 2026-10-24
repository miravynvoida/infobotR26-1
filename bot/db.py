"""Слой данных: SQLite. Один процесс (бот + API), доступ под общим локом."""
import json
import re
import secrets
import sqlite3
import threading
from datetime import datetime

from . import config

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fio TEXT NOT NULL,
    fio_norm TEXT NOT NULL UNIQUE COLLATE NOCASE,
    code TEXT NOT NULL UNIQUE,
    tg_id INTEGER UNIQUE,
    authorized_at TEXT,
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS disciplines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_norm TEXT NOT NULL UNIQUE COLLATE NOCASE,
    emoji TEXT NOT NULL DEFAULT '📚',
    teacher TEXT
);
CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    pair_no INTEGER NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    discipline_id INTEGER NOT NULL REFERENCES disciplines(id),
    lesson_type TEXT,
    room TEXT,
    UNIQUE(date, pair_no)
);
CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedule(date);
CREATE INDEX IF NOT EXISTS idx_schedule_disc ON schedule(discipline_id);
CREATE TABLE IF NOT EXISTS homework (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline_id INTEGER NOT NULL REFERENCES disciplines(id),
    title TEXT NOT NULL,
    task_text TEXT NOT NULL,
    due_date TEXT,
    due_type TEXT,
    explanation TEXT,
    files TEXT NOT NULL DEFAULT '[]',
    published_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    created_by INTEGER
);
CREATE INDEX IF NOT EXISTS idx_hw_disc ON homework(discipline_id, archived);
CREATE TABLE IF NOT EXISTS homework_views (
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    homework_id INTEGER NOT NULL REFERENCES homework(id) ON DELETE CASCADE,
    viewed_at TEXT NOT NULL,
    UNIQUE(student_id, homework_id)
);
CREATE TABLE IF NOT EXISTS homework_done (
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    homework_id INTEGER NOT NULL REFERENCES homework(id) ON DELETE CASCADE,
    done_at TEXT NOT NULL,
    UNIQUE(student_id, homework_id)
);
CREATE TABLE IF NOT EXISTS textbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline_id INTEGER NOT NULL REFERENCES disciplines(id),
    title TEXT NOT NULL,
    description TEXT,
    files TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    discipline_id INTEGER NOT NULL REFERENCES disciplines(id),
    date TEXT,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grades_student ON grades(student_id, discipline_id);
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    missing_pairs TEXT NOT NULL DEFAULT '[]',
    responded_at TEXT NOT NULL,
    UNIQUE(date, student_id)
);
CREATE TABLE IF NOT EXISTS notify_settings (
    student_id INTEGER PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
    next_pair INTEGER NOT NULL DEFAULT 1,
    next_pair_min INTEGER NOT NULL DEFAULT 30,
    tomorrow INTEGER NOT NULL DEFAULT 1,
    tomorrow_time TEXT NOT NULL DEFAULT '19:00',
    misc INTEGER NOT NULL DEFAULT 1,
    theme TEXT NOT NULL DEFAULT 'dark'
);
CREATE TABLE IF NOT EXISTS notif_log (
    day TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    UNIQUE(day, kind, key)
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""

SEED_STUDENTS = [
    "Аносов Владимир Сергеевич",
    "Бакин Станислав Михайлович",
    "Борисов Матин Анатольевич",
    "Винокуров Николай Иванович",
    "Волков Дмитрий Вячеславович",
    "Новиков Даниил Александрович",
    "Гринева Полина Алексеевна",
    "Гурьянова Карина Романовна",
    "Дёмин Александр Алексеевич",
    "Шулекин Максим Дмитриевич",
    "Елизаров Артём Витальевич",
    "Звонов Илья Сергеевич",
    "Иванов Фёдор Иванович",
    "Ионов Александр Евгеньевич",
    "Карней Иван Геннадьевич",
    "Куварзин Даниил Александрович",
    "Курагина Маргарита Алексеевна",
    "Морозов Игорь Леонидович",
    "Мурашов Тимур Антонович",
    "Нагорняк Егор Алексеевич",
    "Селезенев Даниил Андреевич",
    "Сироткина Анастасия Алексеевна",
    "Смирнов Евгений Антонович",
    "Тарасов Иван Александрович",
    "Тузов Александр Сергеевич",
]

SEED_DISCIPLINES = [
    ("Биология", "🧬", "Зыкова Д.А."),
    ("География", "🗺", "Иванова Т.А."),
    ("Ин. язык", "🗣", "Балыкина М.И."),
    ("Информатика", "💻", "Шабаев А.А."),
    ("История", "🏛", "Тугова М.А."),
    ("Литература", "📖", "Пронина А.В."),
    ("Математика", "📐", "Иванова Т.А."),
    ("ОБЖиЗР", "🛡", "Груздев И.И."),
    ("Обществознание", "⚖️", "Алексеева Л.М."),
    ("ОПД", "🧩", "Самохвалова Е.Б."),
    ("Родной язык", "📝", "Куркина В.В."),
    ("Русский язык", "✍️", "Пронина А.В."),
    ("Физика", "⚛️", "Апарин Л.А."),
    ("Химия", "🧪", "Зыкова Д.А."),
    ("Физ. культура", "🏃", "Оринчук А.В."),
]

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

DAY_SQL = (
    "SELECT s.*, d.name AS discipline, d.emoji, d.teacher FROM schedule s "
    "JOIN disciplines d ON d.id = s.discipline_id WHERE s.date = ? ORDER BY s.start"
)
HW_SQL = (
    "SELECT h.*, d.name AS discipline, d.emoji, d.teacher FROM homework h "
    "JOIN disciplines d ON d.id = h.discipline_id"
)
TB_SQL = (
    "SELECT t.*, d.name AS discipline, d.emoji FROM textbooks t "
    "JOIN disciplines d ON d.id = t.discipline_id"
)


def norm_fio(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower().replace("ё", "е"))


def norm_name(s: str) -> str:
    return re.sub(r"[\s.\-()]", "", (s or "").strip().lower().replace("ё", "е"))


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- базовые

def connect() -> None:
    global _conn
    if _conn is not None:
        return
    _conn = sqlite3.connect(config.cfg.db_path, check_same_thread=False, timeout=30)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA foreign_keys=ON")


def init() -> None:
    connect()
    with _lock:
        _conn.executescript(SCHEMA)
        # мягкая миграция: колонки, добавленные после первого релиза
        cols = {r["name"] for r in q("PRAGMA table_info(notify_settings)")}
        if "quiet" not in cols:
            _conn.execute("ALTER TABLE notify_settings ADD COLUMN quiet INTEGER NOT NULL DEFAULT 0")
        if "hw_tomorrow" not in cols:
            _conn.execute("ALTER TABLE notify_settings ADD COLUMN hw_tomorrow INTEGER NOT NULL DEFAULT 1")
        if "hw_tomorrow_time" not in cols:
            _conn.execute("ALTER TABLE notify_settings ADD COLUMN hw_tomorrow_time TEXT NOT NULL DEFAULT '18:00'")
        if "admin_mute" not in cols:
            _conn.execute("ALTER TABLE notify_settings ADD COLUMN admin_mute INTEGER NOT NULL DEFAULT 0")
        _conn.commit()
    if not q("SELECT 1 FROM students LIMIT 1"):
        codes: list[tuple[str, str]] = []
        for fio in SEED_STUDENTS:
            codes.append((fio, gen_code()))
        with _lock:
            _conn.executemany(
                "INSERT INTO students(fio, fio_norm, code, created_at) VALUES(?,?,?,?)",
                [(f, norm_fio(f), c, _ts()) for f, c in codes],
            )
            _conn.commit()
        print("=== Сгенерированные коды входа студентов ===")
        for f, c in codes:
            print(f"  {c} — {f}")
        print("===========================================")
    if not q("SELECT 1 FROM disciplines LIMIT 1"):
        with _lock:
            _conn.executemany(
                "INSERT INTO disciplines(name, name_norm, emoji, teacher) VALUES(?,?,?,?)",
                [(n, norm_name(n), e, t) for n, e, t in SEED_DISCIPLINES],
            )
            _conn.commit()
    # Коды входа печатаются при каждом старте — их всегда можно взять из логов контейнера
    print("=== Коды входа студентов (актуальны всегда) ===")
    for r in q("SELECT code, fio FROM students ORDER BY fio"):
        print(f"  {r['code']} — {r['fio']}")
    print("==============================================")


def gen_code() -> str:
    with _lock:
        used = {r["code"] for r in q("SELECT code FROM students")}
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if code not in used:
            return code


def q(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        cur = _conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def one(sql: str, params: tuple = ()) -> dict | None:
    with _lock:
        cur = _conn.execute(sql, params)
        r = cur.fetchone()
        return dict(r) if r else None


def ins(sql: str, params: tuple = ()) -> int:
    with _lock:
        cur = _conn.execute(sql, params)
        _conn.commit()
        return cur.lastrowid


def ex(sql: str, params: tuple = ()) -> int:
    with _lock:
        cur = _conn.execute(sql, params)
        _conn.commit()
        return cur.rowcount


# ---------------------------------------------------------------- студенты

def all_students() -> list[dict]:
    return q("SELECT * FROM students ORDER BY fio")


def student_by_id(sid: int) -> dict | None:
    return one("SELECT * FROM students WHERE id=?", (sid,))


def student_by_tg(tg_id: int) -> dict | None:
    return one("SELECT * FROM students WHERE tg_id=?", (tg_id,))


def student_by_fio(fio: str) -> dict | None:
    return one("SELECT * FROM students WHERE fio_norm=?", (norm_fio(fio),))


def authorized_students() -> list[dict]:
    return q("SELECT * FROM students WHERE tg_id IS NOT NULL ORDER BY fio")


def add_student(fio: str) -> dict:
    code = gen_code()
    sid = ins(
        "INSERT INTO students(fio, fio_norm, code, created_at) VALUES(?,?,?,?)",
        (fio.strip(), norm_fio(fio), code, _ts()),
    )
    return student_by_id(sid)


def link_tg(sid: int, tg_id: int) -> None:
    ex("UPDATE students SET tg_id=?, authorized_at=? WHERE id=?", (tg_id, _ts(), sid))


def unlink_tg(sid: int) -> None:
    ex("UPDATE students SET tg_id=NULL, authorized_at=NULL WHERE id=?", (sid,))


def regen_code(sid: int) -> str:
    code = gen_code()
    ex("UPDATE students SET code=? WHERE id=?", (code, sid))
    return code


def delete_student(sid: int) -> None:
    with _lock:
        for tbl in ("grades", "attendance", "notify_settings"):
            _conn.execute(f"DELETE FROM {tbl} WHERE student_id=?", (sid,))
        _conn.execute("DELETE FROM students WHERE id=?", (sid,))
        _conn.commit()


# ---------------------------------------------------------------- дисциплины

def all_disciplines() -> list[dict]:
    return q("SELECT * FROM disciplines ORDER BY name")


def discipline_by_id(did: int) -> dict | None:
    return one("SELECT * FROM disciplines WHERE id=?", (did,))


def discipline_by_name(name: str) -> dict | None:
    return one("SELECT * FROM disciplines WHERE name_norm=?", (norm_name(name),))


def ensure_discipline(name: str, emoji: str = "📚", teacher: str | None = None) -> int:
    d = discipline_by_name(name)
    if d:
        return d["id"]
    return ins(
        "INSERT INTO disciplines(name, name_norm, emoji, teacher) VALUES(?,?,?,?)",
        (name.strip(), norm_name(name), emoji, teacher),
    )


def discipline_usage(did: int) -> dict:
    return {
        "schedule": one("SELECT COUNT(*) c FROM schedule WHERE discipline_id=?", (did,))["c"],
        "homework": one("SELECT COUNT(*) c FROM homework WHERE discipline_id=?", (did,))["c"],
        "textbooks": one("SELECT COUNT(*) c FROM textbooks WHERE discipline_id=?", (did,))["c"],
        "grades": one("SELECT COUNT(*) c FROM grades WHERE discipline_id=?", (did,))["c"],
    }


# ---------------------------------------------------------------- расписание

def day_lessons(day_iso: str) -> list[dict]:
    return q(DAY_SQL, (day_iso,))


def replace_day(day_iso: str, rows: list[tuple]) -> None:
    """rows: (pair_no, start, end, discipline_id, lesson_type, room)"""
    with _lock:
        _conn.execute("DELETE FROM schedule WHERE date=?", (day_iso,))
        _conn.executemany(
            "INSERT INTO schedule(date,pair_no,start,end,discipline_id,lesson_type,room)"
            " VALUES(?,?,?,?,?,?,?)",
            [(day_iso, *r) for r in rows],
        )
        _conn.commit()


def delete_day(day_iso: str) -> None:
    ex("DELETE FROM schedule WHERE date=?", (day_iso,))


def schedule_dates() -> list[str]:
    return [r["date"] for r in q("SELECT DISTINCT date FROM schedule ORDER BY date")]


def disciplines_with_schedule() -> list[dict]:
    return q(
        "SELECT DISTINCT d.* FROM disciplines d JOIN schedule s ON s.discipline_id=d.id ORDER BY d.name"
    )


# ---------------------------------------------------------------- дз

def active_homework() -> list[dict]:
    return q(HW_SQL + " WHERE h.archived=0 ORDER BY h.due_date, h.published_at")


def archived_homework() -> list[dict]:
    return q(HW_SQL + " WHERE h.archived=1 ORDER BY h.archived_at DESC")


def homework_by_discipline(archived: int = 0) -> list[dict]:
    return q(HW_SQL + " WHERE h.archived=? ORDER BY h.due_date, h.published_at", (archived,))


def hw_by_id(hid: int) -> dict | None:
    return one(HW_SQL + " WHERE h.id=?", (hid,))


def create_hw(
    discipline_id: int,
    title: str,
    task_text: str,
    due_date: str | None,
    due_type: str | None,
    explanation: str | None,
    files: list[dict],
    published_at: str,
    created_by: int | None,
) -> int:
    return ins(
        "INSERT INTO homework(discipline_id,title,task_text,due_date,due_type,explanation,"
        "files,published_at,created_by) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            discipline_id,
            title,
            task_text,
            due_date,
            due_type,
            explanation,
            json.dumps(files, ensure_ascii=False),
            published_at,
            created_by,
        ),
    )


def update_hw(hid: int, **fields) -> None:
    if "files" in fields and isinstance(fields["files"], list):
        fields["files"] = json.dumps(fields["files"], ensure_ascii=False)
    keys = ", ".join(f"{k}=?" for k in fields)
    ex(f"UPDATE homework SET {keys} WHERE id=?", (*fields.values(), hid))


def set_hw_archived(hid: int, archived: bool, when: str | None = None) -> None:
    ex(
        "UPDATE homework SET archived=?, archived_at=? WHERE id=?",
        (1 if archived else 0, when if archived else None, hid),
    )


def delete_hw(hid: int) -> None:
    with _lock:
        _conn.execute("DELETE FROM homework_views WHERE homework_id=?", (hid,))
        _conn.execute("DELETE FROM homework_done WHERE homework_id=?", (hid,))
        _conn.execute("DELETE FROM homework WHERE id=?", (hid,))
        _conn.commit()


def archive_due_homework(day_iso: str, when: str) -> int:
    return ex(
        "UPDATE homework SET archived=1, archived_at=? WHERE archived=0 AND due_date=?",
        (when, day_iso),
    )


def hw_due_on(day_iso: str) -> list[dict]:
    return q(HW_SQL + " WHERE h.archived=0 AND h.due_date=? ORDER BY d.name, h.due_date", (day_iso,))


def mark_viewed(sid: int, hid: int, when: str) -> None:
    ex(
        "INSERT OR IGNORE INTO homework_views(student_id,homework_id,viewed_at) VALUES(?,?,?)",
        (sid, hid, when),
    )


def unviewed_hw_ids(sid: int) -> set[int]:
    rows = q(
        "SELECT h.id FROM homework h WHERE h.archived=0 AND h.id NOT IN"
        " (SELECT homework_id FROM homework_views WHERE student_id=?)",
        (sid,),
    )
    return {r["id"] for r in rows}


def done_hw_ids(sid: int) -> set[int]:
    return {r["homework_id"] for r in q("SELECT homework_id FROM homework_done WHERE student_id=?", (sid,))}


def set_hw_done(sid: int, hid: int, done: bool, when: str) -> None:
    if done:
        ex(
            "INSERT OR IGNORE INTO homework_done(student_id,homework_id,done_at) VALUES(?,?,?)",
            (sid, hid, when),
        )
    else:
        ex("DELETE FROM homework_done WHERE student_id=? AND homework_id=?", (sid, hid))


# ---------------------------------------------------------------- учебники

def all_textbooks() -> list[dict]:
    return q(TB_SQL + " ORDER BY d.name, t.title")


def textbooks_by_discipline(did: int) -> list[dict]:
    return q(TB_SQL + " WHERE t.discipline_id=? ORDER BY t.title", (did,))


def textbook_by_id(tid: int) -> dict | None:
    return one(TB_SQL + " WHERE t.id=?", (tid,))


def create_textbook(discipline_id: int, title: str, description: str | None, files: list[dict]) -> int:
    return ins(
        "INSERT INTO textbooks(discipline_id,title,description,files,created_at) VALUES(?,?,?,?,?)",
        (discipline_id, title, description, json.dumps(files, ensure_ascii=False), _ts()),
    )


def update_textbook(tid: int, **fields) -> None:
    if "files" in fields and isinstance(fields["files"], list):
        fields["files"] = json.dumps(fields["files"], ensure_ascii=False)
    keys = ", ".join(f"{k}=?" for k in fields)
    ex(f"UPDATE textbooks SET {keys} WHERE id=?", (*fields.values(), tid))


def delete_textbook(tid: int) -> None:
    ex("DELETE FROM textbooks WHERE id=?", (tid,))


# ---------------------------------------------------------------- оценки

def replace_discipline_grades(did: int, rows: list[tuple]) -> None:
    with _lock:
        _conn.execute("DELETE FROM grades WHERE discipline_id=?", (did,))
        _conn.executemany(
            "INSERT INTO grades(student_id,discipline_id,date,value) VALUES(?,?,?,?)",
            [(sid, did, d, v) for sid, d, v in rows],
        )
        _conn.commit()


def student_grades(sid: int) -> list[dict]:
    return q(
        "SELECT g.*, d.name AS discipline, d.emoji FROM grades g "
        "JOIN disciplines d ON d.id=g.discipline_id WHERE g.student_id=? ORDER BY g.date",
        (sid,),
    )


def student_stats(sid: int) -> dict:
    vals = [r["value"] for r in q("SELECT value FROM grades WHERE student_id=?", (sid,))]
    nums = [int(v) for v in vals if v in ("2", "3", "4", "5")]
    return {
        "avg": round(sum(nums) / len(nums), 2) if nums else None,
        "total": len(nums),
        "h": vals.count("Н"),
        "b": vals.count("Б"),
        "o": vals.count("О"),
    }


# ---------------------------------------------------------------- посещаемость

def set_attendance(day_iso: str, sid: int, status: str, missing: list[int] | None, when: str) -> None:
    ex(
        "INSERT INTO attendance(date,student_id,status,missing_pairs,responded_at) VALUES(?,?,?,?,?)"
        " ON CONFLICT(date,student_id) DO UPDATE SET status=excluded.status,"
        " missing_pairs=excluded.missing_pairs, responded_at=excluded.responded_at",
        (day_iso, sid, status, json.dumps(missing or []), when),
    )


def get_attendance(day_iso: str, sid: int) -> dict | None:
    return one("SELECT * FROM attendance WHERE date=? AND student_id=?", (day_iso, sid))


def reset_attendance(day_iso: str, sid: int) -> None:
    ex("DELETE FROM attendance WHERE date=? AND student_id=?", (day_iso, sid))


def day_attendance(day_iso: str) -> list[dict]:
    return q(
        "SELECT a.*, s.fio FROM attendance a JOIN students s ON s.id=a.student_id WHERE a.date=?",
        (day_iso,),
    )


# ---------------------------------------------------------------- настройки

def get_settings(sid: int) -> dict:
    row = one("SELECT * FROM notify_settings WHERE student_id=?", (sid,))
    if row:
        return row
    ins("INSERT INTO notify_settings(student_id) VALUES(?)", (sid,))
    return one("SELECT * FROM notify_settings WHERE student_id=?", (sid,))


def update_settings(sid: int, **fields) -> None:
    get_settings(sid)
    keys = ", ".join(f"{k}=?" for k in fields)
    ex(f"UPDATE notify_settings SET {keys} WHERE student_id=?", (*fields.values(), sid))


def all_notify_settings() -> list[dict]:
    return q("SELECT n.*, s.tg_id, s.fio FROM notify_settings n JOIN students s ON s.id=n.student_id WHERE s.tg_id IS NOT NULL")


def set_mute(sid: int, muted: bool) -> None:
    get_settings(sid)
    ex("UPDATE notify_settings SET admin_mute=? WHERE student_id=?", (1 if muted else 0, sid))


def is_muted(sid: int) -> bool:
    row = one("SELECT admin_mute FROM notify_settings WHERE student_id=?", (sid,))
    return bool(row and row["admin_mute"])


def muted_tg_ids() -> set[int]:
    return {
        r["tg_id"]
        for r in q(
            "SELECT s.tg_id FROM notify_settings n JOIN students s ON s.id=n.student_id"
            " WHERE n.admin_mute=1 AND s.tg_id IS NOT NULL"
        )
    }


def notif_once(day: str, kind: str, key: str) -> bool:
    """True, если это уведомление ещё не отправлялось (и помечаем его отправленным)."""
    with _lock:
        cur = _conn.execute(
            "INSERT OR IGNORE INTO notif_log(day,kind,key) VALUES(?,?,?)", (day, kind, key)
        )
        _conn.commit()
        return cur.rowcount == 1


# ---------------------------------------------------------------- kv

def kv_get(key: str, default: str = "") -> str:
    row = one("SELECT value FROM kv WHERE key=?", (key,))
    return row["value"] if row else default


def kv_set(key: str, value: str) -> None:
    ex("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def kv_items(prefix: str) -> list[tuple[str, str]]:
    return [(r["key"], r["value"]) for r in q("SELECT key, value FROM kv WHERE key LIKE ?", (prefix + "%",))]


def kv_delete(key: str) -> None:
    ex("DELETE FROM kv WHERE key=?", (key,))


def checkpoint() -> None:
    """Слить WAL в основной файл (для бэкапа)."""
    with _lock:
        _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _conn.commit()


def swap_database(new_path: str) -> None:
    """Подменить базу файла (бэкап/восстановление) и переподключиться."""
    global _conn
    with _lock:
        _conn.commit()
        _conn.close()
        import shutil

        shutil.copyfile(new_path, config.cfg.db_path)
        _conn = None
    connect()
