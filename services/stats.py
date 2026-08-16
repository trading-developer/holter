from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass
class StatsResult:
    count: int
    sys_avg: int | None
    sys_min: int | None
    sys_max: int | None
    dia_avg: int | None
    dia_min: int | None
    dia_max: int | None
    pulse_count: int
    pulse_avg: int | None
    pulse_min: int | None
    pulse_max: int | None
    last_at_utc: datetime | None


def format_stats(result: StatsResult, days: int, tz: ZoneInfo) -> str:
    if result.count == 0:
        return f"📊 Статистика за {days} дн.\n\nПока нет записей за период."

    lines = [f"📊 Статистика за {days} дн. (записей: {result.count})", ""]
    lines.append(f"САД:   сред {result.sys_avg} · мин {result.sys_min} · макс {result.sys_max}")
    lines.append(f"ДАД:   сред {result.dia_avg} · мин {result.dia_min} · макс {result.dia_max}")
    if result.pulse_count == 0:
        lines.append("Пульс: нет данных")
    else:
        lines.append(
            f"Пульс: сред {result.pulse_avg} · мин {result.pulse_min} · макс {result.pulse_max}"
            f"   (по {result.pulse_count} замерам)"
        )
    lines.append("")
    if result.last_at_utc is not None:
        local = result.last_at_utc.astimezone(tz)
        lines.append(f"Последняя запись: {local.strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(lines)
