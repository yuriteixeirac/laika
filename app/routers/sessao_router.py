from collections.abc import Sequence
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import utils
from app.models import Mensagem, Sessao
from app.schemas.sessao_schemas import SessaoUpdateSchema

sessao_router = APIRouter(prefix="/sessao")


@sessao_router.get("/")
async def list_sessoes(request: Request, db: AsyncSession = Depends(utils.get_db)):
    sessoes = await db.scalars(
        select(Sessao).where(
            Sessao.usuario == await utils.get_current_user(request, db)
        )
    )
    return sessoes.all()


@sessao_router.get("/{sessao_id}")
async def get_sessao(
    sessao_id: int, request: Request, db: AsyncSession = Depends(utils.get_db)
):
    usuario = await utils.get_current_user(request, db)

    sessao = await db.scalar(
        select(Sessao).where(Sessao.id == sessao_id, Sessao.usuario == usuario)
    )

    if not sessao:
        raise HTTPException(status_code=404, detail="sessão não existente.")

    return sessao


@sessao_router.put("/{sessao_id}")
async def atualizar_sessao(
    sessao_update: SessaoUpdateSchema,
    request: Request,
    sessao_id: int,
    db: AsyncSession = Depends(utils.get_db),
):
    usuario = await utils.get_current_user(request, db)

    sessao = await db.scalar(
        select(Sessao).where(Sessao.id == sessao_id, Sessao.usuario == usuario)
    )

    if not sessao:
        raise HTTPException(status_code=404, detail="sessão não encontrada.")

    sessao.titulo = sessao_update.titulo
    sessao.atualizado_em = datetime.now()

    db.add(sessao)
    await db.commit()


@sessao_router.delete("/{sessao_id}")
async def deletar_sessao(
    request: Request, sessao_id: int, db: AsyncSession = Depends(utils.get_db)
):
    usuario = await utils.get_current_user(request, db)

    sessao = await db.scalar(
        select(Sessao).where(Sessao.id == sessao_id, Sessao.usuario == usuario)
    )

    if not sessao:
        raise HTTPException(status_code=404, detail="sessão não encontrada.")

    await db.delete(sessao)
    await db.commit()


@sessao_router.get("/{sessao_id}/mensagens")
async def get_mensagens(
    request: Request, sessao_id: int, db: AsyncSession = Depends(utils.get_db)
):
    usuario = await utils.get_current_user(request, db)

    sessao = await db.scalar(
        select(Sessao).where(Sessao.id == sessao_id, Sessao.usuario == usuario)
    )

    if not sessao:
        raise HTTPException(status_code=404, detail="sessão não encontrada.")

    return sessao.mensagens
