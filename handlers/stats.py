from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from db import repo
from handlers.history import format_history
from services.stats import format_stats


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    await repo.ensure_user(tg_id)
    since_utc = datetime.now(timezone.utc) - timedelta(days=settings.stats_days)
    result = await repo.stats(tg_id, since_utc)
    tz = ZoneInfo(settings.timezone)
    await update.message.reply_html(format_stats(result, settings.stats_days, tz))


async def show_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    await repo.ensure_user(tg_id)
    tz = ZoneInfo(settings.timezone)

    since_utc = datetime.now(timezone.utc) - timedelta(days=settings.stats_days)
    result = await repo.stats(tg_id, since_utc)
    stats_text = format_stats(result, settings.stats_days, tz)

    rows = await repo.list_recent(tg_id, settings.history_limit)
    history_text = format_history(rows, tz)

    await update.message.reply_html(f"{stats_text}\n\n{history_text}")
