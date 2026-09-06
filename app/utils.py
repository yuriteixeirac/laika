from sqlalchemy.ext.asyncio import AsyncSession

from app import engine


async def get_db():
    async with AsyncSession(engine) as session:
        return session
