from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config import settings


def day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    tz = ZoneInfo(settings.timezone)
    local = now_utc.astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


class LimitError(Exception):
    """Человекочитаемое сообщение в .args[0]."""


def check_limits(last_created_at: datetime | None, count_today: int, now_utc: datetime) -> None:
    s = settings
    if count_today >= s.max_per_day:
        raise LimitError(f"На сегодня достигнут лимит {s.max_per_day} записей.")
    if last_created_at is not None:
        delta = (now_utc - last_created_at).total_seconds()
        if delta < s.min_interval_seconds:
            raise LimitError(f"Слишком часто. Подожди ещё {int(s.min_interval_seconds - delta)} с.")
