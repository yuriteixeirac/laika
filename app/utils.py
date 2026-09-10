from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine
from app.models.usuario import Usuario


async def get_db() -> AsyncGenerator[AsyncSession, Any]:
    async with AsyncSession(engine) as session:
        yield session


async def get_current_user(request: Request, db: AsyncSession) -> Usuario:
    user_id = int(request.session.get("user_id", 0))
    if not user_id:
        raise HTTPException(status_code=401, detail="usuário não logado.")

    usuario = await db.scalar(select(Usuario).where(Usuario.id == user_id))

    if not usuario:
        raise HTTPException(status_code=404, detail="usuário não existente.")

    return usuario
