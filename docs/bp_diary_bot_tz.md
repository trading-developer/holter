# ТЗ: Telegram-бот «Дневник давления» (bp_diary_bot)

Документ предназначен для исполнения ИИ-агентом. Всё, что помечено `CONFIG`, выносится в
настройки и не хардкодится. Комментарии в коде и тексты интерфейса — на русском.

**Изменения этой ревизии:** асинхронная БД (`aiosqlite` + async SQLAlchemy 2.0); пульс —
необязательное поле; добавлен блок напоминаний о замере с настройками и отключением.

> ⚠️ Бот — это журнал измерений, а не медицинское устройство. Он **не** ставит диагнозов, **не**
> трактует значения и **не** выдаёт «нормы». Пороги валидации ниже — только защита от опечаток.

---

## 0. Область и цель

Персональный бот-дневник артериального давления. Пользователь в любой момент присылает строку
вида `120 80 75` (САД, ДАД, пульс) или `120 80` (без пульса). Бот валидирует, спрашивает
самочувствие (с возможностью пропустить), сохраняет запись, ведёт статистику, строит график,
показывает историю, умеет чистить старые данные и напоминать о замере по расписанию.

---

## 1. Стек и зависимости

- Python **3.11+**
- `python-telegram-bot[job-queue]==22.8` — асинхронный фреймворк Bot API (актуальная стабильная
  на 08.2026). Extra `[job-queue]` тянет APScheduler, без него `application.job_queue is None`.
- `SQLAlchemy[asyncio]>=2.0,<2.1` — ORM, **асинхронный** движок
- `aiosqlite>=0.20` — async-драйвер SQLite
- `matplotlib>=3.8` — график (backend `Agg`, без GUI)
- `pydantic-settings>=2.0` — конфигурация из `.env`
- `tzdata` — база таймзон для `zoneinfo` (обязательно на Windows)

`requirements.txt`:
```
python-telegram-bot[job-queue]==22.8
SQLAlchemy[asyncio]>=2.0,<2.1
aiosqlite>=0.20
matplotlib>=3.8
pydantic-settings>=2.0
tzdata
```

Вся работа с БД асинхронная — хендлеры вызывают репозиторий напрямую через `await`, без
`to_thread`. SQLite всё равно сериализует запись, но event loop не блокируется.

---

## 2. Структура проекта

```
bp_diary_bot/
├── requirements.txt
├── .env.example
├── README.md
├── bot.py                # точка входа: Application, Defaults(tzinfo), post_init, хендлеры
├── config.py             # pydantic-settings Settings
├── keyboards.py          # inline-клавиатуры (самочувствие, очистка, настройки)
├── db/
│   ├── __init__.py
│   ├── engine.py         # async engine, SessionLocal, init_db()
│   ├── models.py         # User, Measurement, Reminder
│   └── repo.py           # асинхронные CRUD/агрегации
├── services/
│   ├── __init__.py
│   ├── parsing.py        # разбор и валидация строки замера (пульс опционален)
│   ├── limits.py         # проверка лимитов (10/день, 1 мин)
│   ├── stats.py          # расчёт статистики
│   ├── charts.py         # генерация PNG-графика
│   └── reminders.py      # планирование/снятие job'ов напоминаний через JobQueue
└── handlers/
    ├── __init__.py
    ├── common.py         # /start, /help, глобальный error handler
    ├── add.py            # ConversationHandler «мастер добавления»
    ├── stats.py          # /stats, /show
    ├── history.py        # /history
    ├── graph.py          # /graph
    ├── clear.py          # /clear
    └── settings.py       # /settings: напоминания (вкл/выкл, добавить/убрать время)
```

---

## 3. Конфигурация (`config.py`)

`pydantic-settings`, источник — `.env`. Пороги и лимиты — `CONFIG`.

| Поле | Тип | Дефолт | Назначение |
|---|---|---|---|
| `bot_token` | str | — (обязательно) | токен бота |
| `db_url` | str | `sqlite+aiosqlite:///bp_diary.db` | async-строка подключения |
| `timezone` | str | `Europe/Moscow` | таймзона для «дня», отображения и напоминаний |
| `max_per_day` | int | `10` | максимум записей в календарный день |
| `min_interval_seconds` | int | `60` | минимальный интервал между записями |
| `sys_min` / `sys_max` | int | `50` / `300` | границы САД (анти-опечатка) |
| `dia_min` / `dia_max` | int | `30` / `250` | границы ДАД (анти-опечатка) |
| `pulse_min` / `pulse_max` | int | `20` / `300` | границы пульса (если введён) |
| `require_sys_gt_dia` | bool | `true` | отклонять записи, где САД ≤ ДАД |
| `stats_days` | int | `7` | окно статистики по умолчанию |
| `history_limit` | int | `15` | сколько строк показывать в истории |
| `graph_days` | int | `30` | окно графика по умолчанию |
| `max_reminders_per_user` | int | `5` | лимит времён напоминаний на пользователя |

`.env.example`:
```
BOT_TOKEN=
DB_URL=sqlite+aiosqlite:///bp_diary.db
TIMEZONE=Europe/Moscow
MAX_PER_DAY=10
MIN_INTERVAL_SECONDS=60
```

Метки времени в БД — **в UTC**. Конвертация в `timezone` только на границах: отображение,
вычисление «календарного дня» для лимита, расчёт времени напоминаний.

---

## 4. Модель данных (`db/models.py`)

SQLAlchemy 2.0, типизированный стиль. `pulse` теперь nullable. Добавлены `Reminder` и флаг
`reminders_enabled` в `User`.

```python
from datetime import datetime, timezone
from sqlalchemy import (ForeignKey, SmallInteger, Boolean, DateTime,
                        Index, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    tg_id: Mapped[int] = mapped_column(primary_key=True)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # глобальный тумблер
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    measurements: Mapped[list["Measurement"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    reminders: Mapped[list["Reminder"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


class Measurement(Base):
    __tablename__ = "measurements"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.tg_id", ondelete="CASCADE"), index=True)
    systolic: Mapped[int] = mapped_column(SmallInteger)              # САД
    diastolic: Mapped[int] = mapped_column(SmallInteger)            # ДАД
    pulse: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)   # пульс (опц.)
    feeling: Mapped[int | None] = mapped_column(SmallInteger, nullable=True) # 1..5 или NULL
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="measurements")
    __table_args__ = (Index("ix_measurements_user_created", "user_id", "created_at"),)


class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.tg_id", ondelete="CASCADE"), index=True)
    hour: Mapped[int] = mapped_column(SmallInteger)     # 0..23 (локальное время)
    minute: Mapped[int] = mapped_column(SmallInteger)   # 0..59

    user: Mapped["User"] = relationship(back_populates="reminders")
    __table_args__ = (UniqueConstraint("user_id", "hour", "minute", name="uq_reminder_time"),)
```

`db/engine.py` (асинхронный движок + PRAGMA через sync_engine):
```python
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import settings
from db.models import Base

engine = create_async_engine(settings.db_url, future=True)

# PRAGMA вешаем на нижележащий sync_engine — событие "connect" срабатывает на реальном DBAPI-соединении
@event.listens_for(engine.sync_engine, "connect")
def _fk_pragma(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

**Подводные камни SQLite/tz** (в силе):
- SQLite не хранит tzinfo — при чтении приводить `created_at` к aware-UTC в репозитории;
- `expire_on_commit=False` обязателен, иначе поля ORM-объектов «протухают» после commit.

Миграций для MVP не нужно (`create_all`). Alembic — в дорожной карте.

---

## 5. Разбор и валидация ввода (`services/parsing.py`)

### Формат
**Два или три** целых числа через разделители: пробел(ы), `/`, `,`, `;`.
Валидно: `120 80` (без пульса), `120 80 75`, `120/80/75`, `120,80`, `120 80 75`.

### Алгоритм
```python
import re
from dataclasses import dataclass
from config import settings

SEP = re.compile(r"[\s/,;]+")

@dataclass(frozen=True)
class Parsed:
    systolic: int
    diastolic: int
    pulse: int | None      # None, если не введён

class ParseError(ValueError):
    """Человекочитаемое сообщение в .args[0]."""

def parse_measurement(text: str) -> Parsed:
    tokens = [t for t in SEP.split(text.strip()) if t]
    if len(tokens) not in (2, 3):
        raise ParseError("Нужно 2 или 3 числа: САД ДАД [пульс]. Примеры: 120 80  или  120 80 75")
    try:
        nums = [int(t) for t in tokens]
    except ValueError:
        raise ParseError("Значения должны быть целыми числами. Пример: 120 80 75")

    sys_, dia = nums[0], nums[1]
    pul = nums[2] if len(nums) == 3 else None
    s = settings

    if not (s.sys_min <= sys_ <= s.sys_max):
        raise ParseError(f"САД вне диапазона {s.sys_min}–{s.sys_max}. Проверь ввод.")
    if not (s.dia_min <= dia <= s.dia_max):
        raise ParseError(f"ДАД вне диапазона {s.dia_min}–{s.dia_max}. Проверь ввод.")
    if pul is not None and not (s.pulse_min <= pul <= s.pulse_max):
        raise ParseError(f"Пульс вне диапазона {s.pulse_min}–{s.pulse_max}. Проверь ввод.")
    if s.require_sys_gt_dia and sys_ <= dia:
        raise ParseError("САД должно быть больше ДАД — вероятно, опечатка.")
    return Parsed(sys_, dia, pul)
```

«Мягкий» матч-регексп для entry-point (2 или 3 группы; полную проверку делает `parse_measurement`):
```python
MEASUREMENT_RE = re.compile(r"^\s*\d{1,3}[\s/,;]+\d{1,3}(?:[\s/,;]+\d{1,3})?\s*$")
```

---

## 6. Лимиты (`services/limits.py`)

Без изменений по логике: интервал `< min_interval_seconds` и дневной счётчик `>= max_per_day`
(день считается в `timezone`). Проверки — **до** запроса самочувствия.

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from config import settings

def day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    tz = ZoneInfo(settings.timezone)
    local = now_utc.astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

class LimitError(Exception): ...

def check_limits(last_created_at, count_today, now_utc) -> None:
    s = settings
    if count_today >= s.max_per_day:
        raise LimitError(f"На сегодня достигнут лимит {s.max_per_day} записей.")
    if last_created_at is not None:
        delta = (now_utc - last_created_at).total_seconds()
        if delta < s.min_interval_seconds:
            raise LimitError(f"Слишком часто. Подожди ещё {int(s.min_interval_seconds - delta)} с.")
```

---

## 7. Репозиторий (`db/repo.py`) — асинхронный

Все функции `async`, используют `AsyncSession` из `SessionLocal`. Пример:
```python
async def add_measurement(tg_id, systolic, diastolic, pulse, feeling) -> Measurement:
    async with SessionLocal() as s:
        m = Measurement(user_id=tg_id, systolic=systolic, diastolic=diastolic,
                        pulse=pulse, feeling=feeling)
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m
```

Сигнатуры:
```python
# пользователи
async def ensure_user(tg_id: int) -> None
async def get_user(tg_id: int) -> User | None
async def set_reminders_enabled(tg_id: int, enabled: bool) -> None
# замеры
async def last_created_at(tg_id: int) -> datetime | None            # aware UTC
async def count_today(tg_id: int, start_utc, end_utc) -> int
async def add_measurement(tg_id, systolic, diastolic, pulse, feeling) -> Measurement
async def list_recent(tg_id: int, limit: int) -> list[Measurement]  # DESC
async def list_range(tg_id: int, since_utc) -> list[Measurement]    # ASC (график/статистика)
async def stats(tg_id: int, since_utc) -> StatsResult               # см. §10
async def delete_older_than(tg_id: int, cutoff_utc) -> int
async def delete_all(tg_id: int) -> int
# напоминания
async def list_reminders(tg_id: int) -> list[Reminder]              # ASC по (hour, minute)
async def add_reminder(tg_id: int, hour: int, minute: int) -> bool  # False, если дубль/лимит
async def remove_reminder(tg_id: int, hour: int, minute: int) -> None
async def all_reminder_targets() -> list[tuple[int, bool, list[tuple[int, int]]]]
    # (tg_id, reminders_enabled, [(hour, minute), ...]) — для восстановления при старте
```

Агрегации (`count_today`, `stats`) считать в SQL (`func.count/avg/min/max`). Пульс — только по
не-NULL строкам (см. §10). При чтении `created_at` приводить к aware-UTC.

---

## 8. Сценарии и команды

| Команда | Действие |
|---|---|
| `/start` | приветствие + справка, `ensure_user` |
| `/help` | формат ввода и список команд |
| `/add` | явный запуск мастера добавления |
| `/stats` | статистика за `stats_days` |
| `/history` | последние `history_limit` записей таблицей |
| `/graph` | график за `graph_days` |
| `/show` | «показать сразу»: статистика **и** таблица одним ответом |
| `/clear` | меню очистки старых данных |
| `/settings` | **напоминания**: вкл/выкл, добавить/убрать время |
| `/cancel` | прервать текущий мастер |
| строка `120 80` / `120 80 75` | запускает мастер добавления |

Зарегистрировать команды через `set_my_commands`.

---

## 9. Мастер добавления (`handlers/add.py`)

`ConversationHandler`, два входа (`/add` и `MessageHandler(MEASUREMENT_RE)`), одно состояние
`FEELING`.

### Поток
```
entry: /add без чисел ──► «Пришли замер строкой: 120 80 или 120 80 75» ──► END
entry: строка с числами ─► parse_measurement()
                              ├─ ошибка ──► текст ошибки ──► END
                              └─ ок ──► check_limits()
                                          ├─ лимит ──► текст ──► END
                                          └─ ок ──► user_data["pending"]={sys,dia,pul}
                                                    показать клавиатуру самочувствия
                                                    STATE = FEELING
STATE FEELING: CallbackQuery feel:1..5 / feel:skip
              ──► add_measurement(..., feeling)  (feel:skip → None)
              ──► подтверждение ──► END
fallback: /cancel ──► очистить user_data, «Отменено» ──► END
```

- значения замера между шагами — в `context.user_data["pending"]`;
- при входе через `/add` без чисел строка-замер придёт новым апдейтом и повторно войдёт через
  `MEASUREMENT_RE`;
- `per_message=False`, `per_chat=True`, `per_user=True`; предупреждение PTB о трекинге callback —
  ожидаемо и безопасно; в каждом callback обязательно `await query.answer()`.

### Клавиатура самочувствия (заложенные кнопки, `keyboards.py`)
Ряд 1: `😀 Отлично` `🙂 Хорошо` `😐 Норм`
Ряд 2: `😕 Так себе` `🤒 Плохо`
Ряд 3: `⏭ Пропустить`
`callback_data`: `feel:5` `feel:4` `feel:3` `feel:2` `feel:1` `feel:skip` (skip → `feeling=None`).

### Подтверждение
```
✅ Записано: 120/80, пульс 75, самочувствие 🙂
Сегодня записей: 3/10
```
Если пульс не вводился: `✅ Записано: 120/80, пульс —, самочувствие 🙂`.

---

## 10. Статистика (`services/stats.py`)

Окно — последние `stats_days` дней. Метрики по САД/ДАД/пульс: `count`, `avg` (округл. до целого),
`min`, `max`. Пульс агрегируется **только по не-NULL** значениям, поэтому у него отдельный
счётчик `pulse_count` (может быть меньше общего `count`).

```python
@dataclass
class StatsResult:
    count: int
    sys_avg: int | None; sys_min: int | None; sys_max: int | None
    dia_avg: int | None; dia_min: int | None; dia_max: int | None
    pulse_count: int
    pulse_avg: int | None; pulse_min: int | None; pulse_max: int | None
    last_at_utc: datetime | None
```

Вывод (HTML):
```
📊 Статистика за 7 дн. (записей: 14)

САД:   сред 128 · мин 118 · макс 141
ДАД:   сред 82 · мин 74 · макс 90
Пульс: сред 71 · мин 63 · макс 79   (по 12 замерам)

Последняя запись: 16.08.2026 09:14
```
При `count == 0` — «Пока нет записей за период». Если `pulse_count == 0` — строку пульса заменить
на «Пульс: нет данных».

---

## 11. История (`handlers/history.py`)

Последние `history_limit` записей (DESC), моноширинная таблица в `<pre>` (HTML).

```
<pre>
Дата/время     САД ДАД Пульс Сам.
16.08 09:14    120  80   75   🙂
15.08 21:03    131  84    —   😐
15.08 08:12    118  76   68   —
</pre>
```
- время — локальная tz, формат `dd.MM HH:mm`;
- `feeling`: `1..5 → 🤒 😕 😐 🙂 😀`, `None → —`;
- `pulse`: `None → —`;
- ширины колонок фиксировать (`f"{v:>3}"`), для `None` подставлять `"—"`.

---

## 12. График (`services/charts.py`)

- `matplotlib.use("Agg")` **до** импорта `pyplot`;
- окно `graph_days`, данные `list_range` ASC;
- САД и ДАД — по всем точкам; **пульс — отдельная серия только из точек, где `pulse is not None`**
  (со своими x), чтобы пропуски не рисовались как ноль/разрыв;
- PNG в `io.BytesIO` (`dpi=120`), `reply_photo`; после сохранения `plt.close(fig)`;
- при пустых данных — текст «Недостаточно данных для графика», фото не слать.

```python
xs = [r.created_at.astimezone(tz) for r in rows]
ax.plot(xs, [r.systolic for r in rows], marker="o", label="САД")
ax.plot(xs, [r.diastolic for r in rows], marker="o", label="ДАД")
pulse_pts = [(r.created_at.astimezone(tz), r.pulse) for r in rows if r.pulse is not None]
if pulse_pts:
    px, py = zip(*pulse_pts)
    ax.plot(px, py, marker="o", label="Пульс")
```

---

## 13. `/show` — «показать сразу»

Одно действие = два блока в одном ответе: блок статистики (§10) + таблица истории (§11).
Переиспользовать функции форматирования, логику не дублировать. Опционально следом — график.

---

## 14. Очистка данных (`handlers/clear.py`)

`/clear` → inline-меню:
Ряд 1: `🗑 Старше 30 дней` `🗑 Старше 90 дней`
Ряд 2: `🗑 Удалить всё` `✖️ Отмена`
`callback_data`: `clr:30` `clr:90` `clr:all` `clr:cancel`.

- `clr:30`/`clr:90` → `delete_older_than(now_utc - N дней)`, ответ «Удалено N записей».
- `clr:all` → **шаг подтверждения** (`clr:all_yes` / `clr:cancel`), затем `delete_all`.
- `clr:cancel` → «Отменено», снять клавиатуру. Всегда `await query.answer()`.

---

## 15. Напоминания (`handlers/settings.py` + `services/reminders.py`)

### Что делает
Напоминает пользователю сделать замер в заданное(ые) время суток (локальная `timezone`).
Глобальный тумблер `reminders_enabled` ставит все напоминания пользователя на паузу без удаления
времён. По умолчанию времён нет — пока пользователь не добавит, ничего не приходит (без спама).

### Хранение и источник истины
Времена и тумблер — в БД (`Reminder`, `User.reminders_enabled`). Job'ы `JobQueue` живут в памяти
и теряются при перезапуске, поэтому **при старте бот пересобирает job'ы из БД** (`schedule_all`).

### Планирование (`services/reminders.py`)
```python
from datetime import time as dtime
from zoneinfo import ZoneInfo
from config import settings

def _job_name(tg_id, h, m) -> str:
    return f"rem:{tg_id}:{h:02d}:{m:02d}"

def remove_user_jobs(job_queue, tg_id: int) -> None:
    prefix = f"rem:{tg_id}:"
    for job in list(job_queue.jobs()):
        if job.name and job.name.startswith(prefix):
            job.schedule_removal()

def schedule_user(job_queue, tg_id: int, enabled: bool, times: list[tuple[int, int]]) -> None:
    remove_user_jobs(job_queue, tg_id)          # сначала снять старые
    if not enabled:
        return
    tz = ZoneInfo(settings.timezone)
    for h, m in times:
        job_queue.run_daily(
            reminder_callback,
            time=dtime(hour=h, minute=m, tzinfo=tz),   # tzinfo привязываем явно
            chat_id=tg_id,
            name=_job_name(tg_id, h, m),
        )

async def reminder_callback(context) -> None:
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text="🔔 Пора измерить давление. Пришли строку, например: <b>120 80 75</b>",
        parse_mode="HTML",
    )

async def schedule_all(app) -> None:                  # вызывать из post_init
    from db import repo
    for tg_id, enabled, times in await repo.all_reminder_targets():
        schedule_user(app.job_queue, tg_id, enabled, times)
```

> `run_daily(time=...)`: если у `time` не задан `tzinfo`, JobQueue берёт таймзону бота (UTC, если
> не выставлен `Defaults.tzinfo`). Мы задаём `tzinfo` явно → срабатывание в локальное время.
> Про переход на летнее/зимнее время расчёт делегируется APScheduler.

### Экран `/settings` (`handlers/settings.py`)
`ConversationHandler` с состоянием `ADD_TIME`. При открытии показывает текущее состояние:
```
⚙️ Напоминания: включены
Времена: 09:00, 21:00
```
Клавиатура:
Ряд 1: `🔔 Выключить` (или `🔕 Включить`) — callback `set:toggle`
Ряд 2: `➕ Добавить время` `set:add`   `🗑 Убрать время` `set:del`
Ряд 3: `✖️ Закрыть` `set:close`

- `set:toggle` → инвертировать `reminders_enabled`, `set_reminders_enabled`, затем
  `schedule_user(...)` с актуальным флагом и временами, перерисовать экран.
- `set:add` → перейти в `ADD_TIME`, попросить «Введи время в формате ЧЧ:ММ (например 09:00)».
  Пришедший текст парсить (`^([01]?\d|2[0-3]):([0-5]\d)$`), при ошибке — сообщение и остаться в
  `ADD_TIME`. При успехе: проверить лимит `max_reminders_per_user`, `add_reminder`
  (дубликат игнорируется), `schedule_user(...)`, вернуться к экрану, END состояния.
- `set:del` → показать клавиатуру со списком текущих времён (`callback_data` `del:HH:MM`) +
  «Отмена»; по выбору — `remove_reminder`, `schedule_user(...)`, перерисовать.
- `set:close` → убрать клавиатуру.
- всегда `await query.answer()`; после операций пересобирать job'ы данного пользователя.

---

## 16. Точка входа (`bot.py`)

```python
from zoneinfo import ZoneInfo
from telegram.ext import ApplicationBuilder, Defaults
from config import settings
from db.engine import init_db
from services.reminders import schedule_all

async def post_init(app) -> None:
    await init_db()
    await schedule_all(app)        # восстановить напоминания из БД
    await app.bot.set_my_commands([...])

def main() -> None:
    app = (ApplicationBuilder()
           .token(settings.bot_token)
           .defaults(Defaults(tzinfo=ZoneInfo(settings.timezone)))
           .post_init(post_init)
           .build())
    # register_handlers(app): common, add(ConversationHandler), stats, history,
    #                          graph, clear, settings(ConversationHandler), error_handler
    # ВАЖНО: ConversationHandler'ы регистрировать раньше «широкого» MessageHandler,
    #        чтобы entry-point замера не перехватывался чем-то ещё.
    app.run_polling()
```
Проверить `app.job_queue is not None` (иначе не установлен extra `[job-queue]`).

---

## 17. Форматирование, ошибки, логирование

- `parse_mode="HTML"` везде (таблицы — `<pre>`); пользовательский текст — `html.escape`.
- `ParseError`/`LimitError` — ожидаемые ветки, ловятся в хендлере, отвечают текстом из `.args[0]`;
  не доходят до глобального error handler.
- Глобальный `add_error_handler`: логировать traceback, пользователю — «Что-то пошло не так».
- `logging` уровня INFO с временем и именем логгера.

---

## 18. Подводные камни (обязательно учесть)

1. **Время в БД — UTC**; конвертация в локаль на границах; «день» и напоминания — в `timezone`.
2. **PRAGMA foreign_keys=ON** через listener на `engine.sync_engine` — иначе `CASCADE` не работает.
3. **Async-сессии**: не переиспользовать одну сессию между задачами; `expire_on_commit=False`.
4. **`matplotlib.use("Agg")` до `pyplot`** и `plt.close(fig)` после графика.
5. **`await query.answer()`** в каждом `CallbackQueryHandler`.
6. **JobQueue в памяти** — источник истины БД; восстанавливать job'ы в `post_init`.
7. **tzinfo у `run_daily`** задавать явно; extra `[job-queue]` обязателен (иначе `job_queue is None`).
8. **Порядок хендлеров**: `ConversationHandler` мастера добавления — до широкого текстового
   хендлера; `/cancel` — общий fallback.
9. **Пульс nullable**: везде обрабатывать `None` (валидация, статистика по не-NULL, история/график).
10. **Границы валидации — не медицинские нормы**; не подписывать как «норма/высокое».
11. **tzdata на Windows** — без пакета `zoneinfo` не найдёт таймзону.
12. **aiosqlite**: `db_url` должен начинаться с `sqlite+aiosqlite:///`, иначе движок не асинхронный.

---

## 19. Дорожная карта (фазы)

- **Фаза 1 (MVP):** config, async engine, модели, `init_db`, репозиторий, парсинг (пульс опц.),
  лимиты, мастер добавления, `/start /help /add /cancel`. Запись работает end-to-end.
- **Фаза 2:** `/history`, `/stats`, `/show`.
- **Фаза 3:** `/graph`.
- **Фаза 4:** `/clear` с подтверждением.
- **Фаза 5:** напоминания — `Reminder`, `/settings`, `services/reminders`, `schedule_all` в
  `post_init`.
- **Фаза 6 (позже):** Alembic; «не напоминать, если сегодня уже измерял»; экспорт CSV; выбор
  периода статистики кнопками; самочувствие как линия на графике.

---

## 20. Критерии приёмки (чек-лист)

- [ ] `120 80`, `120 80 75`, `120/80/75`, `120,80` парсятся корректно; `120 80` даёт `pulse=NULL`.
- [ ] `120` (1 число) и `120 80 abc` → понятная ошибка, запись не создаётся.
- [ ] `70 120` (САД ≤ ДАД) отклоняется при `require_sys_gt_dia=true`.
- [ ] `400 80` (САД вне границ) отклоняется с указанием диапазона.
- [ ] 11-я запись за день отклоняется (`10/10`); вторая за минуту — с остатком секунд.
- [ ] После валидного замера — клавиатура самочувствия; `⏭ Пропустить` → `feeling=NULL`.
- [ ] Запись видна в `/history`; `feeling=NULL` и `pulse=NULL` рендерятся как `—`.
- [ ] `/stats`: count/avg/min/max по САД/ДАД; пульс — по не-NULL с отдельным счётчиком.
- [ ] `/graph`: линии САД/ДАД по всем точкам, пульс — только по не-NULL; пусто → текст, не фото.
- [ ] `/show`: статистика и таблица вместе.
- [ ] `/clear` «Старше 30 дней» удаляет только старые и сообщает число; «Удалить всё» требует
      подтверждения.
- [ ] `/settings`: тумблер вкл/выкл работает; добавление времени `09:00` создаёт job; напоминание
      приходит в локальное время; удаление времени снимает job.
- [ ] Лимит `max_reminders_per_user` соблюдается; дубликат времени не создаёт вторую запись.
- [ ] После перезапуска бота напоминания восстанавливаются из БД; данные не теряются.
- [ ] `PRAGMA foreign_keys=ON` активен (удаление пользователя каскадит замеры и напоминания).
- [ ] `db_url` асинхронный; event loop не блокируется на операциях с БД.
