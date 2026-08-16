import re

from telegram import Update
from telegram.ext import (CallbackQueryHandler, CommandHandler,
                           ContextTypes, ConversationHandler, MessageHandler, filters)

from config import settings
from db import repo
from db.models import User
from keyboards import BUTTON_TEXTS_RE, delete_time_keyboard, settings_keyboard

ADD_TIME = 1
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _render_text(user: User, times: list[tuple[int, int]]) -> str:
    status = "включены" if user.reminders_enabled else "выключены"
    times_str = ", ".join(f"{h:02d}:{m:02d}" for h, m in times) if times else "нет"
    return f"⚙️ Напоминания: {status}\nВремена: {times_str}"


async def _current_times(tg_id: int) -> list[tuple[int, int]]:
    return [(r.hour, r.minute) for r in await repo.list_reminders(tg_id)]


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    await repo.ensure_user(tg_id)
    user = await repo.get_user(tg_id)
    times = await _current_times(tg_id)
    await update.message.reply_text(_render_text(user, times), reply_markup=settings_keyboard(user.reminders_enabled))


async def settings_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from services.reminders import schedule_user

    query = update.callback_query
    await query.answer()
    tg_id = update.effective_user.id

    user = await repo.get_user(tg_id)
    new_enabled = not user.reminders_enabled
    await repo.set_reminders_enabled(tg_id, new_enabled)
    times = await _current_times(tg_id)
    schedule_user(context.job_queue, tg_id, new_enabled, times)

    user = await repo.get_user(tg_id)
    await query.edit_message_text(_render_text(user, times), reply_markup=settings_keyboard(user.reminders_enabled))


async def settings_del_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tg_id = update.effective_user.id

    times = await _current_times(tg_id)
    if not times:
        user = await repo.get_user(tg_id)
        await query.edit_message_text(_render_text(user, times), reply_markup=settings_keyboard(user.reminders_enabled))
        return
    await query.edit_message_text("Выбери время для удаления:", reply_markup=delete_time_keyboard(times))


async def settings_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Закрыто")


async def del_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from services.reminders import schedule_user

    query = update.callback_query
    await query.answer()
    tg_id = update.effective_user.id
    _, h, m = query.data.split(":")
    await repo.remove_reminder(tg_id, int(h), int(m))

    user = await repo.get_user(tg_id)
    times = await _current_times(tg_id)
    schedule_user(context.job_queue, tg_id, user.reminders_enabled, times)
    await query.edit_message_text(_render_text(user, times), reply_markup=settings_keyboard(user.reminders_enabled))


async def add_time_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введи время в формате ЧЧ:ММ (например 09:00)")
    return ADD_TIME


async def add_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from services.reminders import schedule_user

    tg_id = update.effective_user.id
    match = TIME_RE.match(update.message.text.strip())
    if not match:
        await update.message.reply_text("Неверный формат. Введи время в формате ЧЧ:ММ (например 09:00)")
        return ADD_TIME

    hour, minute = int(match.group(1)), int(match.group(2))
    ok = await repo.add_reminder(tg_id, hour, minute)

    user = await repo.get_user(tg_id)
    times = await _current_times(tg_id)
    schedule_user(context.job_queue, tg_id, user.reminders_enabled, times)

    if not ok:
        await update.message.reply_text(
            f"Не удалось добавить (дубликат или лимит {settings.max_reminders_per_user}).")
    await update.message.reply_text(_render_text(user, times), reply_markup=settings_keyboard(user.reminders_enabled))
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено")
    return ConversationHandler.END


def build_add_time_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(add_time_start, pattern=r"^set:add$")],
        states={
            ADD_TIME: [MessageHandler(
                filters.TEXT & ~filters.COMMAND & ~filters.Regex(BUTTON_TEXTS_RE), add_time_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        per_chat=True,
        per_user=True,
        # нажатие кнопки меню во время ввода времени не матчит состояние ADD_TIME и провалится
        # к обработчику кнопки; таймаут подчищает зависшую сессию диалога
        conversation_timeout=180,
    )
