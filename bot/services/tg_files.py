"""Файлы через Telegram Bot API (httpx): отправка по file_id, загрузка для получения file_id."""
import httpx

from .. import config
from . import schedule_utils as su

API_BASE = f"https://api.telegram.org/bot{config.cfg.bot_token}"

# type -> (метод Bot API, поле с file_id)
SEND_MAP = {
    "document": ("sendDocument", "document"),
    "photo": ("sendPhoto", "photo"),
    "video": ("sendVideo", "video"),
    "audio": ("sendAudio", "audio"),
    "animation": ("sendAnimation", "animation"),
    "voice": ("sendVoice", "voice"),
    "video_note": ("sendVideoNote", "video_note"),
}


async def api_call(method: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=120) as cli:
        r = await cli.post(f"{API_BASE}/{method}", json=payload)
        data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram API error"))
    return data["result"]


async def send_message_html(chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> dict:
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return await api_call("sendMessage", payload)


async def send_file_by_id(chat_id: int, desc: dict) -> bool:
    method, field = SEND_MAP.get(desc.get("type", "document"), SEND_MAP["document"])
    try:
        await api_call(method, {"chat_id": chat_id, field: desc["file_id"]})
        return True
    except RuntimeError:
        if method != "sendDocument":
            try:
                await api_call("sendDocument", {"chat_id": chat_id, "document": desc["file_id"]})
                return True
            except RuntimeError:
                return False
        return False


async def send_files(chat_id: int, files: list[dict]) -> int:
    sent = 0
    for f in files or []:
        if await send_file_by_id(chat_id, f):
            sent += 1
    return sent


def detect_type(content_type: str, filename: str) -> str:
    ct = (content_type or "").lower()
    name = (filename or "").lower()
    if ct == "image/gif" or name.endswith(".gif"):
        return "animation"
    if ct.startswith("image/"):
        return "photo"
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("audio/"):
        return "audio"
    return "document"


async def upload_get_file_id(chat_id: int, filename: str, content: bytes, content_type: str) -> dict:
    """Отправляет файл в чат (админа), забирает file_id и удаляет сообщение."""
    ftype = detect_type(content_type, filename)
    method, field = SEND_MAP[ftype]
    async with httpx.AsyncClient(timeout=180) as cli:
        r = await cli.post(
            f"{API_BASE}/{method}",
            data={"chat_id": chat_id},
            files={field: (filename or "file", content, content_type or "application/octet-stream")},
        )
        data = r.json()
        if not data.get("ok") and ftype != "document":
            ftype, method, field = "document", "sendDocument", "document"
            r = await cli.post(
                f"{API_BASE}/{method}",
                data={"chat_id": chat_id},
                files={field: (filename or "file", content, content_type or "application/octet-stream")},
            )
            data = r.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description", "Не удалось загрузить файл"))
        msg = data["result"]
        try:
            await cli.post(
                f"{API_BASE}/deleteMessage", json={"chat_id": chat_id, "message_id": msg["message_id"]}
            )
        except Exception:
            pass
    if ftype == "photo":
        file_id = msg["photo"][-1]["file_id"]
    else:
        file_id = msg[ftype]["file_id"]
    return {"type": ftype, "name": filename or "файл", "file_id": file_id}


def hw_notice_html(hw: dict, disc: dict) -> str:
    lines = [
        "📚 <b>Новое домашнее задание!</b>",
        "",
        f"{disc.get('emoji') or '📚'} <b>{su.esc(disc['name'])}</b>",
        f"«{su.esc(hw['title'])}»",
    ]
    if hw.get("due_date"):
        lines.append(f"📅 Сдать до {su.fmt_dmy(hw['due_date'])} ({su.wd_lower(hw['due_date'])})")
    return "\n".join(lines)
