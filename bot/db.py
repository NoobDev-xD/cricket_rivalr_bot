from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession
)
from sqlalchemy import text

from bot.config import settings
from bot.models import Base


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)


async def init_db():

    async with engine.begin() as conn:

        # Create missing tables
        await conn.run_sync(
            Base.metadata.create_all
        )

        # Railway PostgreSQL migration
        if engine.dialect.name == "postgresql":

            await conn.execute(text("""
                ALTER TABLE matches
                ADD COLUMN IF NOT EXISTS host_id BIGINT
            """))

            await conn.execute(text("""
                UPDATE matches
                SET host_id = created_by
                WHERE host_id IS NULL
            """))


async def close_db():
    await engine.dispose()
    
