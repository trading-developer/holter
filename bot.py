import logging
import warnings
from zoneinfo import ZoneInfo

from telegram import BotCommand
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, Defaults, MessageHandler, filters
from telegram.warnings import PTBUserWarning

import handlers.add as add
import handlers.clear as clear
import handlers.common as common
import handlers.graph as graph
import handlers.history as history
import handlers.settings as settings_h
import handlers.stats as stats
from config import settings
from db.engine import init_db
from keyboards import BTN_ADD, BTN_CLEAR, BTN_GRAPH, BTN_HELP, BTN_HISTORY, BTN_SETTINGS, BTN_SHOW, BTN_STATS
from services.reminders import schedule_all

# ConversationHandler с per_message=False + CallbackQueryHandler внутри состояния всегда
# предупреждает о трекинге callback'ов — у нас это безопасно (в каждом состоянии только один тип
# хендлера), поэтому глушим именно этот класс предупреждений, а не warnings целиком.
warnings.filterwarnings("ignore", category=PTBUserWarning, message=r"If 'per_message=False'")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app) -> None:
    await init_db()
    await schedule_all(app)  # восстановить напоминания из БД
    # Основной UX — кнопки постоянной клавиатуры (main_menu_keyboard); из команд оставлены
    # только служебные, остальное продублировано хендлерами команд ниже для совместимости.
    await app.bot.set_my_commands([
        BotCommand("start", "Приветствие и меню"),
        BotCommand("help", "Помощь"),
        BotCommand("cancel", "Отменить действие"),
    ])


def register_handlers(app) -> None:
    # ВАЖНО: ConversationHandler'ы — раньше «широкого» текстового хендлера замера,
    # чтобы entry-point не перехватывался чем-то ещё.
    app.add_handler(add.build_handler())
    app.add_handler(settings_h.build_add_time_handler())

    app.add_handler(CommandHandler("start", common.start))
    app.add_handler(CommandHandler("help", common.help_cmd))
    app.add_handler(CommandHandler("stats", stats.stats_cmd))
    app.add_handler(CommandHandler("history", history.history_cmd))
    app.add_handler(CommandHandler("graph", graph.graph_cmd))
    app.add_handler(CommandHandler("show", stats.show_cmd))
    app.add_handler(CommandHandler("clear", clear.clear_cmd))
    app.add_handler(CommandHandler("settings", settings_h.settings_cmd))

    # постоянная reply-клавиатура — основной способ управления ботом
    app.add_handler(MessageHandler(filters.Text([BTN_ADD]), add.add_button))
    app.add_handler(MessageHandler(filters.Text([BTN_STATS]), stats.stats_cmd))
    app.add_handler(MessageHandler(filters.Text([BTN_HISTORY]), history.history_cmd))
    app.add_handler(MessageHandler(filters.Text([BTN_GRAPH]), graph.graph_cmd))
    app.add_handler(MessageHandler(filters.Text([BTN_SHOW]), stats.show_cmd))
    app.add_handler(MessageHandler(filters.Text([BTN_CLEAR]), clear.clear_cmd))
    app.add_handler(MessageHandler(filters.Text([BTN_SETTINGS]), settings_h.settings_cmd))
    app.add_handler(MessageHandler(filters.Text([BTN_HELP]), common.help_cmd))

    app.add_handler(CallbackQueryHandler(clear.clear_callback, pattern=r"^clr:"))
    app.add_handler(CallbackQueryHandler(settings_h.settings_toggle_callback, pattern=r"^set:toggle$"))
    app.add_handler(CallbackQueryHandler(settings_h.settings_del_menu_callback, pattern=r"^set:del$"))
    app.add_handler(CallbackQueryHandler(settings_h.settings_close_callback, pattern=r"^set:close$"))
    app.add_handler(CallbackQueryHandler(settings_h.del_time_callback, pattern=r"^del:"))

    app.add_error_handler(common.error_handler)


def main() -> None:
    app = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .defaults(Defaults(tzinfo=ZoneInfo(settings.timezone)))
        .post_init(post_init)
        .build()
    )
    assert app.job_queue is not None, "JobQueue недоступен — не установлен extra [job-queue]"
    register_handlers(app)
    app.run_polling()


if __name__ == "__main__":
    main()
