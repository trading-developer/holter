from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from db import repo
from services.charts import build_chart


async def graph_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    await repo.ensure_user(tg_id)
    days = settings.graph_days
    since_utc = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await repo.list_range(tg_id, since_utc)
    tz = ZoneInfo(settings.timezone)
    buf = build_chart(rows, tz, days)
    if buf is None:
        await update.message.reply_text("Недостаточно данных для графика.")
        return
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M")
    await update.message.reply_photo(
        buf, caption=f"📈 Давление и пульс за последние {days} дн.\n🕐 {now}")
