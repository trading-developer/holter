import re

from telegram import Update
from telegram.ext import (CallbackQueryHandler, CommandHandler,
                           ContextTypes, ConversationHandler, MessageHandler, filters)

from config import settings
from db import repo
from db.models import User
from keyboards import BUTTON_TEXTS_RE, delete_time_keyboard, settings_keyboard

ADD_TIME = 1
# ЧЧ:ММ, но терпим к разделителю: 9:00, 09.00, 9-00
TIME_RE = re.compile(r"^([01]?\d|2[0-3])[:.\-]([0-5]\d)$")
# несколько времён одним сообщением: «09:00 22:00», «9:00, 22:00», «9:00 и 22:00»
_TOKEN_SEP = re.compile(r"[\s,;]+")
_NOISE = {"и", "в", "на"}

ADD_TIME_PROMPT = ("Введи время в формате ЧЧ:ММ (например 09:00).\n"
                    "Можно несколько сразу: 09:00 22:00")


def _render_text(user: User, times: list[tuple[int, int]]) -> str:
    status = "включены" if user.reminders_enabled else "выключены"
    times_str = ", ".join(f"{h:02d}:{m:02d}" for h, m in times) if times else "нет"
    return (f"⚙️ Напоминания: {status}\n"
            f"Времена ({len(times)}/{settings.max_reminders_per_user}): {times_str}")


def _parse_times(text: str) -> tuple[list[tuple[int, int]], list[str]]:
    """Разбирает сообщение в список времён; второй элемент — нераспознанные куски."""
    times: list[tuple[int, int]] = []
    bad: list[str] = []
    for token in _TOKEN_SEP.split(text.strip()):
        if not token or token.lower() in _NOISE:
            continue
        match = TIME_RE.match(token)
        if match is None:
            bad.append(token)
            continue
        value = (int(match.group(1)), int(match.group(2)))
        if value not in times:
            times.append(value)
    return times, bad


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
    await query.edit_message_text(ADD_TIME_PROMPT)
    return ADD_TIME


async def add_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from services.reminders import schedule_user

    tg_id = update.effective_user.id
    wanted, bad = _parse_times(update.message.text)
    if not wanted:
        await update.message.reply_text(f"Неверный формат. {ADD_TIME_PROMPT}")
        return ADD_TIME

    added: list[str] = []
    skipped: list[str] = []
    for hour, minute in wanted:
        label = f"{hour:02d}:{minute:02d}"
        (added if await repo.add_reminder(tg_id, hour, minute) else skipped).append(label)

    user = await repo.get_user(tg_id)
    times = await _current_times(tg_id)
    schedule_user(context.job_queue, tg_id, user.reminders_enabled, times)

    report = []
    if added:
        report.append("Добавлено: " + ", ".join(added))
    if skipped:
        report.append(f"Пропущено (дубликат или лимит {settings.max_reminders_per_user}): "
                       + ", ".join(skipped))
    if bad:
        report.append("Не понял: " + ", ".join(bad))
    if report:
        await update.message.reply_text("\n".join(report))

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
