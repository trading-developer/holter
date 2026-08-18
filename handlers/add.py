from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (CallbackQueryHandler, CommandHandler,
                           ContextTypes, ConversationHandler, MessageHandler, filters)

from config import settings
from db import repo
from keyboards import FEELING_EMOJI, feeling_keyboard
from services.limits import LimitError, check_limits, day_bounds_utc
from services.parsing import MEASUREMENT_RE, ParseError, parse_measurement
from services.stickers import pick_sticker, send_sticker

FEELING = 1


async def add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        return await _process_measurement(update, context, " ".join(context.args))
    await update.message.reply_text("Пришли замер строкой: 120 80  или  120 80 75")
    return ConversationHandler.END


async def add_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Пришли замер строкой: 120 80  или  120 80 75")


async def measurement_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _process_measurement(update, context, update.message.text)


async def _process_measurement(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    tg_id = update.effective_user.id
    await repo.ensure_user(tg_id)

    try:
        parsed = parse_measurement(text)
    except ParseError as e:
        await update.message.reply_text(str(e.args[0]))
        return ConversationHandler.END

    now_utc = datetime.now(timezone.utc)
    last_at = await repo.last_created_at(tg_id)
    start_utc, end_utc = day_bounds_utc(now_utc)
    count = await repo.count_today(tg_id, start_utc, end_utc)
    try:
        check_limits(last_at, count, now_utc)
    except LimitError as e:
        await update.message.reply_text(str(e.args[0]))
        return ConversationHandler.END

    context.user_data["pending"] = {
        "systolic": parsed.systolic, "diastolic": parsed.diastolic, "pulse": parsed.pulse,
    }
    await update.message.reply_text("Как самочувствие?", reply_markup=feeling_keyboard())
    return FEELING


async def feeling_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":", 1)[1]
    feeling = None if data == "skip" else int(data)

    pending = context.user_data.pop("pending", None)
    if pending is None:
        await query.edit_message_text("Сессия истекла, начни заново.")
        return ConversationHandler.END

    tg_id = update.effective_user.id
    m = await repo.add_measurement(
        tg_id, pending["systolic"], pending["diastolic"], pending["pulse"], feeling)

    now_utc = datetime.now(timezone.utc)
    start_utc, end_utc = day_bounds_utc(now_utc)
    count = await repo.count_today(tg_id, start_utc, end_utc)

    pulse_text = str(m.pulse) if m.pulse is not None else "—"
    feeling_text = FEELING_EMOJI.get(feeling, "—")
    text = (
        f"✅ Записано: {m.systolic}/{m.diastolic}, пульс {pulse_text}, самочувствие {feeling_text}\n"
        f"Сегодня записей: {count}/{settings.max_per_day}"
    )
    await query.edit_message_text(text)

    # реакция стикером: набор выбирается по категории давления, плохое самочувствие
    # сдвигает тон вниз; отсутствие подходящего стикера — штатная ситуация
    sticker = pick_sticker(m.systolic, m.diastolic, feeling,
                            exclude=context.user_data.get("last_sticker"))
    if sticker and await send_sticker(context.bot, update.effective_chat.id, sticker):
        context.user_data["last_sticker"] = sticker

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending", None)
    await update.message.reply_text("Отменено")
    return ConversationHandler.END


def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("add", add_entry),
            MessageHandler(filters.Regex(MEASUREMENT_RE), measurement_entry),
        ],
        states={
            FEELING: [CallbackQueryHandler(feeling_chosen, pattern=r"^feel:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        per_chat=True,
        per_user=True,
        conversation_timeout=180,  # если самочувствие не выбрано — не виснуть в состоянии навечно
    )
