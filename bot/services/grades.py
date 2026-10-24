"""Синхронизация оценок из Google Таблицы.

Структура таблицы: лист = дисциплина, столбец A — номер, B — ФИО, C+ — даты dd.mm.yyyy,
в ячейках: 2/3/4/5, Н, Б, О (русские), Зачет, Незачет.
"""
import os
import re
from datetime import datetime

from .. import config, db
from . import schedule_utils as su

MARK_MAP = {
    "н": "Н", "б": "Б", "о": "О",
    "зачет": "Зачет", "незачет": "Незачет", "зачёт": "Зачет", "незачёт": "Незачет",
}


def parse_mark(raw: str) -> list[str]:
    out = []
    for p in re.split(r"[,;/\s]+", (raw or "").strip()):
        if not p:
            continue
        pl = p.lower().replace("ё", "е")
        pl = {"h": "н", "b": "б", "o": "о"}.get(pl, pl)
        if pl in ("2", "3", "4", "5"):
            out.append(pl)
        elif pl in ("2.0", "3.0", "4.0", "5.0"):
            out.append(pl[0])
        elif pl in MARK_MAP:
            out.append(MARK_MAP[pl])
    return out


def parse_header_date(raw: str) -> str | None:
    s = (raw or "").strip()[:10]
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def sync_grades() -> dict:
    if not config.cfg.google_sheet_id:
        return {"ok": False, "error": "Не задан GOOGLE_SHEET_ID"}
    if not config.cfg.google_sa_file or not os.path.exists(config.cfg.google_sa_file):
        return {"ok": False, "error": f"Не найден файл сервисного аккаунта: {config.cfg.google_sa_file}"}
    try:
        import gspread

        gc = gspread.service_account(filename=config.cfg.google_sa_file)
        sheet = gc.open_by_key(config.cfg.google_sheet_id)
        worksheets = sheet.worksheets()
    except Exception as e:
        return {"ok": False, "error": f"Google API: {e}"}

    disciplines = db.all_disciplines()
    by_norm = {db.norm_name(d["name"]): d for d in disciplines}
    students = db.all_students()
    students_by_norm = {r["fio_norm"]: r for r in students}

    report = {
        "ok": True, "sheets": 0, "marks": 0, "disciplines": [],
        "unknown_sheets": [], "unknown_fio": [], "skipped_columns": 0,
    }

    for ws in worksheets:
        title = (ws.title or "").strip()
        disc = by_norm.get(db.norm_name(title))
        if disc is None:
            report["unknown_sheets"].append(title)
            continue
        try:
            values = ws.get_all_values()
        except Exception as e:
            report["unknown_sheets"].append(f"{title} (ошибка чтения: {e})")
            continue
        if not values:
            continue
        header = values[0]
        date_cols: dict[int, str] = {}
        for idx, cell in enumerate(header):
            if idx < 2:
                continue
            diso = parse_header_date(cell)
            if diso:
                date_cols[idx] = diso
            elif (cell or "").strip():
                report["skipped_columns"] += 1

        rows_to_insert: list[tuple] = []
        report["sheets"] += 1
        report["disciplines"].append(disc["name"])
        for row in values[1:]:
            fio = row[1].strip() if len(row) > 1 else ""
            if not fio:
                continue
            st = students_by_norm.get(db.norm_fio(fio))
            if st is None:
                if fio not in report["unknown_fio"]:
                    report["unknown_fio"].append(fio)
                continue
            for col, diso in date_cols.items():
                raw = row[col].strip() if len(row) > col else ""
                for mark in parse_mark(raw):
                    rows_to_insert.append((st["id"], diso, mark))
        db.replace_discipline_grades(disc["id"], rows_to_insert)
        report["marks"] += len(rows_to_insert)

    db.kv_set("last_grades_sync", su.ts())
    return report
