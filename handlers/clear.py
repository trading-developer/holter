from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from db import repo
from keyboards import clear_confirm_keyboard, clear_keyboard


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Что удалить?", reply_markup=clear_keyboard())


async def clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    tg_id = update.effective_user.id

    if action == "cancel":
        await query.edit_message_text("Отменено")
        return
    if action == "all":
        await query.edit_message_text("Точно удалить все записи?", reply_markup=clear_confirm_keyboard())
        return
    if action == "all_yes":
        n = await repo.delete_all(tg_id)
        await query.edit_message_text(f"Удалено {n} записей.")
        return
    if action in ("30", "90"):
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(action))
        n = await repo.delete_older_than(tg_id, cutoff)
        await query.edit_message_text(f"Удалено {n} записей.")
        return
