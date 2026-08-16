# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

Персональный Telegram-бот «Дневник давления» (`bp_diary_bot`). Пользователь присылает строку вида
`120 80 75` (САД, ДАД, пульс — пульс опционален), бот валидирует, спрашивает самочувствие, сохраняет
в SQLite, ведёт статистику, строит график, показывает историю, чистит старые данные и умеет
напоминать о замере по расписанию. Полное ТЗ — `docs/bp_diary_bot_tz.md`.

Бот — журнал измерений, а не медицинское устройство: не ставит диагнозов, не трактует значения,
пороги валидации — только защита от опечаток.

## Команды

```bash
# окружение
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# запуск (требует .env, см. .env.example)
.venv/bin/python bot.py

# деплой на сервер (git pull + pip install + pm2 reload)
./gp.sh
```

Тестов, линтера и сборки в проекте нет.

## Конфигурация

`config.py` (`pydantic-settings`) читает `.env`, падает при старте без `BOT_TOKEN`. Остальные поля
(лимиты, диапазоны валидации, таймзона, окна статистики/графика) — см. `.env.example` и таблицу в
ТЗ §3, все дефолты заданы в `Settings`.

## Архитектура

```
bot.py               точка входа: Application, Defaults(tzinfo), post_init, регистрация хендлеров
config.py             pydantic-settings Settings
keyboards.py           постоянная reply-клавиатура (main_menu_keyboard) + inline-клавиатуры
db/engine.py           async engine, SessionLocal, init_db() — PRAGMA foreign_keys через listener
db/models.py            User, Measurement, Reminder (SQLAlchemy 2.0 typed style)
db/repo.py               все CRUD/агрегации, только async
services/parsing.py       разбор и валидация строки замера (пульс опционален)
services/limits.py         дневной лимит + минимальный интервал между записями
services/stats.py           StatsResult + форматирование статистики (HTML)
services/charts.py           matplotlib Agg → PNG в BytesIO, пульс — отдельная серия без пропусков
services/reminders.py         JobQueue: schedule_user/remove_user_jobs/schedule_all
handlers/                     по одному модулю на функциональность (add — ConversationHandler мастера
                                добавления, settings — ConversationHandler только для ввода времени
                                ЧЧ:ММ, остальное в settings — простые CallbackQueryHandler'ы)
```

**Время в БД — всегда UTC**; конвертация в `settings.timezone` только на границах (отображение,
расчёт «дня» для лимита, время напоминаний). Подробный список подводных камней — ТЗ §18
(PRAGMA foreign_keys, expire_on_commit=False, matplotlib.use("Agg") до pyplot, await query.answer(),
JobQueue в памяти — восстанавливается из БД в post_init, tzinfo у run_daily явно, порядок регистрации
хендлеров).

### UX — кнопки, не команды

Основной способ управления — постоянная reply-клавиатура (`keyboards.main_menu_keyboard()`),
отправляется в `/start` и `/help`. Каждая кнопка (`BTN_*` в `keyboards.py`) зарегистрирована в
`bot.py` как `MessageHandler(filters.Text([BTN_X]), ...)` и вызывает ту же функцию, что раньше была
командой (`stats_cmd`, `history_cmd` и т.д.) — она уже работает через `update.message`, поэтому
переиспользуется без изменений. Команды `/stats`, `/history`, `/graph`, `/show`, `/clear`,
`/settings` оставлены зарегистрированными для совместимости, но не входят в `set_my_commands` — из
команд рекламируются только `/start`, `/help`, `/cancel`.

Запись замера по-прежнему не кнопка, а строка `120 80` / `120 80 75`, распознаваемая по regex
(`MEASUREMENT_RE`) — кнопка «➕ Добавить замер» лишь подсказывает формат.

**Ловушка**: состояние `ADD_TIME` в `handlers/settings.py` слушает `filters.TEXT & ~filters.COMMAND`
— без доп. фильтра оно перехватило бы нажатие любой другой кнопки меню как «неверный формат
времени». Исключено через `~filters.Regex(BUTTON_TEXTS_RE)` (из `keyboards.py`): нажатие другой
кнопки не матчит состояние, ConversationHandler возвращает `False`, и update проваливается к
хендлеру этой кнопки. Оба диалоговых `ConversationHandler` (`add`, `settings`) на этот случай ещё
получили `conversation_timeout=180`, чтобы забытая/прерванная сессия не висела вечно.

### Напоминания

Источник истины — БД (`Reminder`, `User.reminders_enabled`); job'ы `JobQueue` живут в памяти и
пересобираются при каждом старте бота (`schedule_all` в `post_init`). Экран `/settings`: команда и
простые callback'и (`set:toggle`, `set:del`, `set:close`, `del:HH:MM`) — плоские хендлеры вне
диалога; ввод нового времени (`set:add` → текст ЧЧ:ММ) — отдельный `ConversationHandler` с
единственным состоянием `ADD_TIME`, т.к. это единственный шаг, которому нужно отслеживать
следующее сообщение пользователя.

### Деплой

PM2 (`ecosystem.config.js`) запускает `bot.py` под `.venv/bin/python`, логи в `logs/`. `gp.sh` —
деплой-скрипт для сервера (структура и принцип — как в соседнем проекте `finex24`); в конце делает
`pm2 save`, чтобы актуальный список процессов попал в дамп.

**Автозапуск после перезагрузки сервера** — `pm2 startup` (разовая настройка, ставит systemd-юнит,
печатает `sudo`-команду, выполняется вручную один раз, не входит в `gp.sh`) отдельно от `pm2 save`
(автоматически в `gp.sh`, сохраняет дамп процессов, который юнит восстановит при загрузке). Без
`pm2 startup` дамп после ребута некому восстановить.
