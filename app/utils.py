from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine
from app.models.usuario import Usuario


async def get_db() -> AsyncGenerator[AsyncSession, Any]:
    async with AsyncSession(engine) as session:
        yield session


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> Usuario | None:
    user_id = request.session.get('user_id')
    if not user_id:
        return None

    return await db.scalar(
        select(Usuario).where(Usuario.id == user_id)
    )
