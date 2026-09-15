import os
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import HTTPException, Request
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine
from app.models.usuario import Usuario

DeepSeekClient = AsyncOpenAI(
    base_url="https://api.deepseek.com", api_key=os.getenv("DEEPSEEK_API_KEY")
)


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


async def gerar_titulo(input: str, output: str) -> str | None:
    res = await DeepSeekClient.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[
            {
                "role": "user",
                "content": f"gera APENAS um titulo de sessão, seu output deve ser SÓ o título, sem markdown, baseado nessas mensagens\n\n{input, output}",
            }
        ],
    )
    print(res.choices[0].message.content)
    return res.choices[0].message.content
