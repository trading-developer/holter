import html
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from db import repo
from db.models import Measurement
from keyboards import FEELING_EMOJI


def format_history(rows: list[Measurement], tz: ZoneInfo) -> str:
    if not rows:
        return "Пока нет записей."
    lines = ["Дата/время     САД ДАД Пульс Сам."]
    for r in rows:
        local = r.created_at.astimezone(tz)
        dt_str = local.strftime("%d.%m %H:%M")
        pulse_str = f"{r.pulse:>3}" if r.pulse is not None else "  —"
        feeling_str = FEELING_EMOJI.get(r.feeling, "—") if r.feeling is not None else "—"
        lines.append(f"{dt_str}  {r.systolic:>3} {r.diastolic:>3}  {pulse_str}   {feeling_str}")
    return "<pre>" + html.escape("\n".join(lines)) + "</pre>"


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    await repo.ensure_user(tg_id)
    rows = await repo.list_recent(tg_id, settings.history_limit)
    tz = ZoneInfo(settings.timezone)
    await update.message.reply_html(format_history(rows, tz))
