import re
from dataclasses import dataclass

from config import settings

SEP = re.compile(r"[\s/,;]+")

# «Мягкий» матч для entry-point ConversationHandler'а: 2 или 3 группы чисел;
# полную валидацию диапазонов делает parse_measurement().
MEASUREMENT_RE = re.compile(r"^\s*\d{1,3}[\s/,;]+\d{1,3}(?:[\s/,;]+\d{1,3})?\s*$")


@dataclass(frozen=True)
class Parsed:
    systolic: int
    diastolic: int
    pulse: int | None


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
