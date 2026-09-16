import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import engine, utils
from app.models.mensagem import Mensagem, Role
from app.models.sessao import Sessao
from app.schemas.chat_schemas import ChatPostSchema

chat_router = APIRouter(prefix="/chat")


@chat_router.post("/")
async def start_chat(
    mensagem: ChatPostSchema,
    request: Request,
    db: AsyncSession = Depends(utils.get_db),
):
    usuario = await utils.get_current_user(request, db)

    sessao = Sessao(titulo="Nova sessão.", usuario_id=usuario.id)

    db.add(sessao)
    await db.flush()

    sessao_id = sessao.id
    sessao_titulo = sessao.titulo

    db.add(Mensagem(conteudo=mensagem.conteudo, role=Role.USER, sessao_id=sessao_id))
    await db.commit()

    async def stream_response(conteudo: str) -> AsyncGenerator[str]:
        yield "event: meta\n"
        yield f"data: {json.dumps({'session_id': sessao_id, 'redirect': f'/chat/{sessao_id}'})}\n\n"

        chunks = []
        try:
            async for event in await utils.DeepSeekClient.chat.completions.create(
                model="deepseek-v4-flash",
                messages=[{"role": "user", "content": conteudo}],
                stream=True,
            ):
                delta = event.choices[0].delta.content or ""
                if delta:
                    chunks.append(delta)
                    yield f"data: {json.dumps({'delta': delta})}\n\n"
        finally:
            output = "".join(chunks)

            novo_titulo = await utils.gerar_titulo(mensagem.conteudo, output)
            async with AsyncSession(engine) as session:
                session.add(
                    Mensagem(sessao_id=sessao_id, conteudo=output, role=Role.ASSISTANT)
                )
                sessao = await session.get(Sessao, sessao_id)
                if sessao:
                    sessao.titulo = novo_titulo if novo_titulo else sessao_titulo

                await session.commit()

        yield f"event: done\ndata: {json.dumps({'title': novo_titulo or sessao_titulo})}\n\n"

    return StreamingResponse(
        stream_response(mensagem.conteudo), media_type="text/event-stream"
    )


@chat_router.post("/{sessao_id}")
async def post_mensagem(
    sessao_id: int,
    mensagem: ChatPostSchema,
    request: Request,
    db: AsyncSession = Depends(utils.get_db),
):
    # usuario = await utils.get_current_user(request, db)

    sessao = await db.scalar(
        select(Sessao).where(Sessao.id == sessao_id, Sessao.usuario_id == 1)
    )

    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    sessao_id = sessao.id

    db.add(Mensagem(conteudo=mensagem.conteudo, role=Role.USER, sessao_id=sessao_id))
    await db.commit()

    async def stream_response(conteudo: str) -> AsyncGenerator[str]:
        yield "event: meta\n"

        chunks = []
        try:
            async for event in await utils.DeepSeekClient.chat.completions.create(
                model="deepseek-v4-flash",
                messages=await utils.get_session_messages(db, sessao_id),  # type: ignore
                stream=True,
            ):
                delta = event.choices[0].delta.content or ""
                if delta:
                    chunks.append(delta)
                    yield f"data: {json.dumps({'delta': delta})}\n\n"
        finally:
            output = "".join(chunks)

            async with AsyncSession(engine) as session:
                session.add(
                    Mensagem(sessao_id=sessao_id, conteudo=output, role=Role.ASSISTANT)
                )
                await session.commit()

        yield "event: done\n\n"

    return StreamingResponse(
        stream_response(mensagem.conteudo), media_type="text/event-stream"
    )
