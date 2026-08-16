from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from config import settings
from db.engine import SessionLocal
from db.models import Measurement, Reminder, User
from services.stats import StatsResult


def _aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# --- пользователи ---

async def ensure_user(tg_id: int) -> None:
    async with SessionLocal() as s:
        user = await s.get(User, tg_id)
        if user is None:
            s.add(User(tg_id=tg_id))
            await s.commit()


async def get_user(tg_id: int) -> User | None:
    async with SessionLocal() as s:
        return await s.get(User, tg_id)


async def set_reminders_enabled(tg_id: int, enabled: bool) -> None:
    async with SessionLocal() as s:
        user = await s.get(User, tg_id)
        if user is not None:
            user.reminders_enabled = enabled
            await s.commit()


# --- замеры ---

async def last_created_at(tg_id: int) -> datetime | None:
    async with SessionLocal() as s:
        result = await s.execute(
            select(Measurement.created_at)
            .where(Measurement.user_id == tg_id)
            .order_by(Measurement.created_at.desc())
            .limit(1)
        )
        return _aware_utc(result.scalar_one_or_none())


async def count_today(tg_id: int, start_utc: datetime, end_utc: datetime) -> int:
    async with SessionLocal() as s:
        result = await s.execute(
            select(func.count(Measurement.id)).where(
                Measurement.user_id == tg_id,
                Measurement.created_at >= start_utc,
                Measurement.created_at <= end_utc,
            )
        )
        return result.scalar_one()


async def add_measurement(tg_id: int, systolic: int, diastolic: int,
                           pulse: int | None, feeling: int | None) -> Measurement:
    async with SessionLocal() as s:
        m = Measurement(user_id=tg_id, systolic=systolic, diastolic=diastolic,
                         pulse=pulse, feeling=feeling)
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m


async def list_recent(tg_id: int, limit: int) -> list[Measurement]:
    async with SessionLocal() as s:
        result = await s.execute(
            select(Measurement).where(Measurement.user_id == tg_id)
            .order_by(Measurement.created_at.desc()).limit(limit)
        )
        rows = list(result.scalars().all())
        for r in rows:
            r.created_at = _aware_utc(r.created_at)
        return rows


async def list_range(tg_id: int, since_utc: datetime) -> list[Measurement]:
    async with SessionLocal() as s:
        result = await s.execute(
            select(Measurement).where(
                Measurement.user_id == tg_id, Measurement.created_at >= since_utc
            ).order_by(Measurement.created_at.asc())
        )
        rows = list(result.scalars().all())
        for r in rows:
            r.created_at = _aware_utc(r.created_at)
        return rows


async def stats(tg_id: int, since_utc: datetime) -> StatsResult:
    async with SessionLocal() as s:
        row = (await s.execute(
            select(
                func.count(Measurement.id),
                func.avg(Measurement.systolic), func.min(Measurement.systolic), func.max(Measurement.systolic),
                func.avg(Measurement.diastolic), func.min(Measurement.diastolic), func.max(Measurement.diastolic),
                func.max(Measurement.created_at),
            ).where(Measurement.user_id == tg_id, Measurement.created_at >= since_utc)
        )).one()
        count, sys_avg, sys_min, sys_max, dia_avg, dia_min, dia_max, last_at = row

        pulse_row = (await s.execute(
            select(
                func.count(Measurement.pulse),
                func.avg(Measurement.pulse), func.min(Measurement.pulse), func.max(Measurement.pulse),
            ).where(
                Measurement.user_id == tg_id,
                Measurement.created_at >= since_utc,
                Measurement.pulse.is_not(None),
            )
        )).one()
        pulse_count, pulse_avg, pulse_min, pulse_max = pulse_row

        return StatsResult(
            count=count or 0,
            sys_avg=round(sys_avg) if sys_avg is not None else None,
            sys_min=sys_min, sys_max=sys_max,
            dia_avg=round(dia_avg) if dia_avg is not None else None,
            dia_min=dia_min, dia_max=dia_max,
            pulse_count=pulse_count or 0,
            pulse_avg=round(pulse_avg) if pulse_avg is not None else None,
            pulse_min=pulse_min, pulse_max=pulse_max,
            last_at_utc=_aware_utc(last_at),
        )


async def delete_older_than(tg_id: int, cutoff_utc: datetime) -> int:
    async with SessionLocal() as s:
        n = (await s.execute(
            select(func.count(Measurement.id)).where(
                Measurement.user_id == tg_id, Measurement.created_at < cutoff_utc
            )
        )).scalar_one()
        await s.execute(
            delete(Measurement).where(
                Measurement.user_id == tg_id, Measurement.created_at < cutoff_utc
            )
        )
        await s.commit()
        return n


async def delete_all(tg_id: int) -> int:
    async with SessionLocal() as s:
        n = (await s.execute(
            select(func.count(Measurement.id)).where(Measurement.user_id == tg_id)
        )).scalar_one()
        await s.execute(delete(Measurement).where(Measurement.user_id == tg_id))
        await s.commit()
        return n


# --- напоминания ---

async def list_reminders(tg_id: int) -> list[Reminder]:
    async with SessionLocal() as s:
        result = await s.execute(
            select(Reminder).where(Reminder.user_id == tg_id)
            .order_by(Reminder.hour, Reminder.minute)
        )
        return list(result.scalars().all())


async def add_reminder(tg_id: int, hour: int, minute: int) -> bool:
    async with SessionLocal() as s:
        count = (await s.execute(
            select(func.count(Reminder.id)).where(Reminder.user_id == tg_id)
        )).scalar_one()
        if count >= settings.max_reminders_per_user:
            return False

        exists = (await s.execute(
            select(Reminder.id).where(
                Reminder.user_id == tg_id, Reminder.hour == hour, Reminder.minute == minute
            )
        )).scalar_one_or_none()
        if exists is not None:
            return False

        s.add(Reminder(user_id=tg_id, hour=hour, minute=minute))
        await s.commit()
        return True


async def remove_reminder(tg_id: int, hour: int, minute: int) -> None:
    async with SessionLocal() as s:
        await s.execute(
            delete(Reminder).where(
                Reminder.user_id == tg_id, Reminder.hour == hour, Reminder.minute == minute
            )
        )
        await s.commit()


async def all_reminder_targets() -> list[tuple[int, bool, list[tuple[int, int]]]]:
    async with SessionLocal() as s:
        users = list((await s.execute(select(User))).scalars().all())
        out = []
        for u in users:
            times = (await s.execute(
                select(Reminder.hour, Reminder.minute).where(Reminder.user_id == u.tg_id)
                .order_by(Reminder.hour, Reminder.minute)
            )).all()
            out.append((u.tg_id, u.reminders_enabled, [(h, m) for h, m in times]))
        return out
