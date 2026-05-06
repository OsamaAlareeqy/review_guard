from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings
import os

# Handle different database URLs
database_url = settings.DATABASE_URL

if database_url.startswith("sqlite"):
    # SQLite doesn't need asyncpg
    async_database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    engine = create_async_engine(
        async_database_url,
        echo=True,
        connect_args={"check_same_thread": False}  # Needed for SQLite
    )
else:
    # PostgreSQL
    async_database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(
        async_database_url,
        echo=True,
        pool_size=10,
        max_overflow=20
    )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()