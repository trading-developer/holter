import logging

from telegram import Update
from telegram.ext import ContextTypes

from db import repo
from keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Пришли строку вида <b>120 80</b> или <b>120 80 75</b> (САД ДАД [пульс]) — начнётся запись.\n\n"
    "Остальное — кнопками внизу экрана:\n"
    "➕ Добавить замер — подсказка по формату\n"
    "📊 Статистика · 📋 История · 📈 График · 🗒 Всё сразу\n"
    "🗑 Очистить — удалить старые данные\n"
    "⚙️ Напоминания — вкл/выкл, время\n\n"
    "/cancel — отменить текущее действие"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await repo.ensure_user(update.effective_user.id)
    await update.message.reply_html(
        f"Привет! Это дневник давления.\n\n{HELP_TEXT}", reply_markup=main_menu_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(HELP_TEXT, reply_markup=main_menu_keyboard())


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Необработанная ошибка", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Что-то пошло не так.")
