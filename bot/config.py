"""Конфигурация: переменные окружения из .env (репозиторий) и data/.env (хостинг)."""
import os
import re
from dataclasses import dataclass
from datetime import date

from dotenv import load_dotenv

# Отметка сборки: показывается в /id и в логах при старте —
# чтобы всегда было видно, какая версия кода реально запущена.
BUILD_TAG = "build-12 (v8)"

load_dotenv()

DATA_DIR = os.getenv("DATA_DIR", "data")
# На хостинге секреты лежат в /app/data/.env — они важнее локального .env
load_dotenv(os.path.join(DATA_DIR, ".env"), override=True)


def _parse_ids(value: str | None) -> frozenset[int]:
    return frozenset(int(x) for x in re.findall(r"\d+", value or ""))


def _parse_date(value: str | None, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    monitor_ids: frozenset[int]
    deputy_ids: frozenset[int]
    webapp_url: str
    support_url: str
    group_name: str
    specialty: str
    app_name: str
    data_dir: str
    db_path: str
    google_sheet_id: str
    google_sa_file: str
    port: int
    first_week_start: date
    attendance_ask_minutes: int
    attendance_remind_minutes: tuple[int, ...]
    attendance_summary_minutes: int
    hw_archive_time: str
    debug_fio: str

    @property
    def staff_ids(self) -> frozenset[int]:
        return self.admin_ids | self.monitor_ids | self.deputy_ids


def _build() -> Config:
    return Config(
        bot_token=os.getenv("BOT_TOKEN", ""),
        admin_ids=_parse_ids(os.getenv("ADMIN_IDS")),
        monitor_ids=_parse_ids(os.getenv("MONITOR_IDS")),
        deputy_ids=_parse_ids(os.getenv("DEPUTY_IDS")),
        webapp_url=os.getenv("WEBAPP_URL", "").strip().rstrip("/"),
        support_url=os.getenv("SUPPORT_URL", "https://t.me/telegram").strip(),
        group_name=os.getenv("GROUP_NAME", "Р 26-1"),
        specialty=os.getenv(
            "SPECIALTY", "Системы радиосвязи, мобильной связи и телерадиовещания"
        ),
        app_name=os.getenv("APP_NAME", "Дневник студента"),
        data_dir=DATA_DIR,
        db_path=os.getenv("DB_PATH") or os.path.join(DATA_DIR, "bot.db"),
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID", "").strip(),
        google_sa_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        or os.path.join(DATA_DIR, "service-account.json"),
        port=int(os.getenv("PORT", "8080")),
        first_week_start=_parse_date(os.getenv("FIRST_WEEK_START"), date(2026, 9, 2)),
        attendance_ask_minutes=int(os.getenv("ATTENDANCE_ASK_MINUTES", "60")),
        attendance_remind_minutes=tuple(
            int(x) for x in os.getenv("ATTENDANCE_REMIND_MINUTES", "40,20,10").split(",")
        ),
        attendance_summary_minutes=int(os.getenv("ATTENDANCE_SUMMARY_MINUTES", "5")),
        hw_archive_time=os.getenv("HW_ARCHIVE_TIME", "18:00"),
        debug_fio=os.getenv("WEBAPP_DEBUG_FIO", "").strip(),
    )


cfg = _build()
os.makedirs(cfg.data_dir, exist_ok=True)
