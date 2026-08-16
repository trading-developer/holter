import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

FEELING_EMOJI = {1: "🤒", 2: "😕", 3: "😐", 4: "🙂", 5: "😀"}

BTN_ADD = "➕ Добавить замер"
BTN_STATS = "📊 Статистика"
BTN_HISTORY = "📋 История"
BTN_GRAPH = "📈 График"
BTN_SHOW = "🗒 Всё сразу"
BTN_CLEAR = "🗑 Очистить"
BTN_SETTINGS = "⚙️ Напоминания"
BTN_HELP = "❓ Помощь"

ALL_BUTTONS = [BTN_ADD, BTN_STATS, BTN_HISTORY, BTN_GRAPH, BTN_SHOW, BTN_CLEAR, BTN_SETTINGS, BTN_HELP]
# используется, чтобы отличить нажатие кнопки меню от ввода времени/др. текста внутри диалогов
BUTTON_TEXTS_RE = re.compile("^(" + "|".join(re.escape(b) for b in ALL_BUTTONS) + ")$")


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BTN_ADD],
            [BTN_STATS, BTN_HISTORY],
            [BTN_GRAPH, BTN_SHOW],
            [BTN_CLEAR, BTN_SETTINGS],
            [BTN_HELP],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def feeling_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("😀 Отлично", callback_data="feel:5"),
         InlineKeyboardButton("🙂 Хорошо", callback_data="feel:4"),
         InlineKeyboardButton("😐 Норм", callback_data="feel:3")],
        [InlineKeyboardButton("😕 Так себе", callback_data="feel:2"),
         InlineKeyboardButton("🤒 Плохо", callback_data="feel:1")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="feel:skip")],
    ])


def clear_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Старше 30 дней", callback_data="clr:30"),
         InlineKeyboardButton("🗑 Старше 90 дней", callback_data="clr:90")],
        [InlineKeyboardButton("🗑 Удалить всё", callback_data="clr:all"),
         InlineKeyboardButton("✖️ Отмена", callback_data="clr:cancel")],
    ])


def clear_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, удалить всё", callback_data="clr:all_yes"),
         InlineKeyboardButton("✖️ Отмена", callback_data="clr:cancel")],
    ])


def settings_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    toggle_label = "🔔 Выключить" if enabled else "🔕 Включить"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data="set:toggle")],
        [InlineKeyboardButton("➕ Добавить время", callback_data="set:add"),
         InlineKeyboardButton("🗑 Убрать время", callback_data="set:del")],
        [InlineKeyboardButton("✖️ Закрыть", callback_data="set:close")],
    ])


def delete_time_keyboard(times: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{h:02d}:{m:02d}", callback_data=f"del:{h:02d}:{m:02d}")]
            for h, m in times]
    rows.append([InlineKeyboardButton("✖️ Отмена", callback_data="set:close")])
    return InlineKeyboardMarkup(rows)
