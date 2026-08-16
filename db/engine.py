from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
