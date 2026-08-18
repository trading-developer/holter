"""Подбор и отправка стикера по результату замера.

Категории давления — международная классификация ESC/ESH 2023 (те же границы
использует ВОЗ). Категорию определяет худший из двух показателей: 150/80 — это
уже 1 степень, хотя ДАД в норме.

Классификация внутренняя: она нужна только чтобы выбрать картинку. Бот
по-прежнему не показывает пользователю названий категорий и не трактует
значения — он журнал измерений, а не медицинское устройство.
"""

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path

from telegram.error import TelegramError, TimedOut

from config import settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Category:
    key: str    # ключ набора стикеров в stickers.json
    tone: str   # грубая группа — запасной ключ, если для категории стикеров нет


# по возрастанию тяжести: (ключ, тон, верхняя граница САД, верхняя граница ДАД)
_GRADES: tuple[tuple[str, str, int, int], ...] = (
    ("optimal",     "positive", 119, 79),
    ("normal",      "positive", 129, 84),
    ("high_normal", "neutral",  139, 89),
    ("grade1",      "negative", 159, 99),
    ("grade2",      "negative", 179, 109),
)
_GRADE3 = Category("grade3", "negative")
_HYPOTENSION = Category("hypotension", "negative")

# плохое самочувствие сдвигает тон на ступень вниз; хорошее ничего не поднимает —
# при плохом давлении весёлый стикер неуместен, даже если человек бодр
_TONE_DOWN = {"positive": "neutral", "neutral": "negative", "negative": "negative"}
_BAD_FEELING_MAX = 2  # 1 «Плохо», 2 «Так себе»

_cache: dict[str, list[str]] = {}
_cache_mtime: float | None = None
_load_failed_logged = False


def classify(systolic: int, diastolic: int) -> Category:
    if systolic < 90 or diastolic < 60:
        return _HYPOTENSION
    for key, tone, sys_max, dia_max in _GRADES:
        if systolic <= sys_max and diastolic <= dia_max:
            return Category(key, tone)
    return _GRADE3


def _stickers_path() -> Path:
    path = Path(settings.stickers_file)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load() -> dict[str, list[str]]:
    """Читает stickers.json, перечитывая только при изменении mtime.

    Файл правится руками (докидываются id стикеров) — перезапуск бота ради этого
    не нужен. Ключи, значение которых не список строк (например `_readme`),
    игнорируются.
    """
    global _cache, _cache_mtime, _load_failed_logged

    path = _stickers_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        if not _load_failed_logged:
            logger.warning("Файл стикеров не найден: %s — стикеры отключены", path)
            _load_failed_logged = True
        return {}

    if mtime == _cache_mtime:
        return _cache

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        if not _load_failed_logged:
            logger.error("Не удалось прочитать %s: %s — стикеры отключены", path, e)
            _load_failed_logged = True
        return _cache

    _cache = {
        key: [s for s in value if isinstance(s, str) and s.strip()]
        for key, value in raw.items()
        if isinstance(value, list)
    }
    _cache_mtime = mtime
    _load_failed_logged = False
    logger.info("Стикеры загружены: %s",
                ", ".join(f"{k}={len(v)}" for k, v in _cache.items() if v) or "пусто")
    return _cache


def pick_sticker(systolic: int, diastolic: int, feeling: int | None = None,
                 exclude: str | None = None) -> str | None:
    """Случайный стикер под замер или None, если подходящих нет.

    Наборы ищутся по цепочке: точная категория → тон (positive/neutral/negative)
    → `any`. Можно заполнить только тона — тогда работает грубое деление
    «хорошо/так себе/плохо»; можно расписать категории — тогда они победят.
    """
    if not settings.stickers_enabled:
        return None

    category = classify(systolic, diastolic)
    tone = category.tone
    if feeling is not None and feeling <= _BAD_FEELING_MAX:
        tone = _TONE_DOWN[tone]

    packs = _load()
    for key in (category.key, tone, "any"):
        ids = packs.get(key)
        if not ids:
            continue
        pool = [s for s in ids if s != exclude] or ids  # не повторять подряд
        return random.choice(pool)
    return None


async def send_sticker(bot, chat_id: int, sticker_id: str, max_retries: int = 3) -> bool:
    """Отправляет стикер. Ошибка отправки не должна ронять запись замера."""
    for attempt in range(max_retries):
        try:
            await bot.send_sticker(chat_id=chat_id, sticker=sticker_id)
            return True
        except TimedOut:
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            logger.error("Стикер не отправлен: таймаут после %d попыток", max_retries)
        except TelegramError as e:
            logger.error("Стикер %s не отправлен: %s", sticker_id, e)
            return False
    return False
