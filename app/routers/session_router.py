from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import utils
from app.models import Sessao

session_router = APIRouter(prefix="/session")


@session_router.get("/")
async def list_sessoes(request: Request, db: AsyncSession = Depends(utils.get_db)):
    usuario = await utils.get_current_user(request)

    sessions = await db.scalars(select(Sessao).where(Sessao.usuario == usuario))

    return sessions
