from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Sessao
from app.utils import get_current_user, get_db

session_router = APIRouter(prefix="/session")


@session_router.get("/")
async def list_sessoes(request: Request, db: AsyncSession = Depends(get_db)):
    usuario = get_current_user(request)

    sessions = db.scalars(
        select(Sessao).where(
            Sessao.usuario == usuario
        )
    )

    return sessions
