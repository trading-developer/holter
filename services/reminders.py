from datetime import time as dtime
from zoneinfo import ZoneInfo

from config import settings


def _job_name(tg_id: int, h: int, m: int) -> str:
    return f"rem:{tg_id}:{h:02d}:{m:02d}"


def remove_user_jobs(job_queue, tg_id: int) -> None:
    prefix = f"rem:{tg_id}:"
    for job in list(job_queue.jobs()):
        if job.name and job.name.startswith(prefix):
            job.schedule_removal()


def schedule_user(job_queue, tg_id: int, enabled: bool, times: list[tuple[int, int]]) -> None:
    remove_user_jobs(job_queue, tg_id)  # сначала снять старые
    if not enabled:
        return
    tz = ZoneInfo(settings.timezone)
    for h, m in times:
        job_queue.run_daily(
            reminder_callback,
            time=dtime(hour=h, minute=m, tzinfo=tz),  # tzinfo привязываем явно
            chat_id=tg_id,
            name=_job_name(tg_id, h, m),
        )


async def reminder_callback(context) -> None:
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text="🔔 Пора измерить давление. Пришли строку, например: <b>120 80 75</b>",
        parse_mode="HTML",
    )


async def schedule_all(app) -> None:  # вызывать из post_init
    from db import repo
    for tg_id, enabled, times in await repo.all_reminder_targets():
        schedule_user(app.job_queue, tg_id, enabled, times)
