from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, SmallInteger, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    tg_id: Mapped[int] = mapped_column(primary_key=True)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
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
    systolic: Mapped[int] = mapped_column(SmallInteger)
    diastolic: Mapped[int] = mapped_column(SmallInteger)
    pulse: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    feeling: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="measurements")
    __table_args__ = (Index("ix_measurements_user_created", "user_id", "created_at"),)


class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.tg_id", ondelete="CASCADE"), index=True)
    hour: Mapped[int] = mapped_column(SmallInteger)
    minute: Mapped[int] = mapped_column(SmallInteger)

    user: Mapped["User"] = relationship(back_populates="reminders")
    __table_args__ = (UniqueConstraint("user_id", "hour", "minute", name="uq_reminder_time"),)
