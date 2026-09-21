import asyncio
import os
from collections.abc import AsyncGenerator, Sequence
from typing import Any

from fastapi import HTTPException, Request
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine
from app.models.chunk import Chunk
from app.models.documento import Documento
from app.models.mensagem import Mensagem
from app.models.usuario import Usuario

DeepSeekClient = AsyncOpenAI(
    base_url="https://api.deepseek.com", api_key=os.getenv("DEEPSEEK_API_KEY")
)

# Quantidade de chunks recuperados do pgvector para montar o contexto do RAG.
RAG_TOP_K = 3

PROMPT_SISTEMA_RAG = (
    "Você é o Laika, um assistente que responde perguntas com base na bibliografia "
    "do curso técnico em informática do IFRN campus Ceará-Mirim.\n"
    "Responda usando exclusivamente o contexto recuperado abaixo e cite o documento "
    "e a página (ex.: 'Nome do documento, p. 12') das informações que utilizar. "
    "Se o contexto não contiver a resposta, diga explicitamente que não encontrou "
    "essa informação na bibliografia e não invente.\n\n"
    "Contexto recuperado:\n"
)

SEM_CONTEXTO = "(nenhum trecho relevante encontrado na bibliografia)"

_embedding_model: Any = None


def get_embedding_model() -> Any:
    """Carrega, uma única vez, o mesmo modelo utilizado na ingestão."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer("intfloat/multilingual-e5-base")
    return _embedding_model


async def embed_texto(texto: str) -> list[float]:
    """Gera o embedding da consulta sem bloquear o event loop."""
    modelo = get_embedding_model()
    embedding = await asyncio.to_thread(
        modelo.encode, texto, normalize_embeddings=True
    )
    return embedding.tolist()


async def recuperar_chunks(
    db: AsyncSession, consulta: str, limite: int = RAG_TOP_K
) -> Sequence[tuple[Chunk, str]]:
    """Busca no pgvector os `limite` chunks mais similares à consulta."""
    embedding = await embed_texto(consulta)

    stmt = (
        select(Chunk, Documento.nome)
        .join(Documento, Chunk.documento_id == Documento.id)
        .order_by(Chunk.embedding.cosine_distance(embedding))
        .limit(limite)
    )

    resultado = await db.execute(stmt)
    return resultado.all()


def formatar_contexto(resultados: Sequence[tuple[Chunk, str]]) -> str:
    """Formata os chunks recuperados como contexto citável para a LLM."""
    if not resultados:
        return SEM_CONTEXTO

    return "\n\n".join(
        f"[{i}] {nome} (página {chunk.pagina}):\n{chunk.conteudo}"
        for i, (chunk, nome) in enumerate(resultados, start=1)
    )


async def recuperar_contexto(db: AsyncSession, consulta: str) -> str:
    """Recupera os melhores chunks da consulta do usuário e monta o contexto."""
    return formatar_contexto(await recuperar_chunks(db, consulta))


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
    return res.choices[0].message.content


async def get_session_messages(
    db: AsyncSession, sessao_id: int, contexto: str | None = None
) -> list[dict]:
    """Monta o histórico da sessão; quando `contexto` é informado, prepende o prompt do RAG."""
    mensagens = await db.scalars(
        select(Mensagem)
        .where(Mensagem.sessao_id == sessao_id)
        .order_by(Mensagem.id)
    )

    output = []
    if contexto is not None:
        output.append(
            {"role": "system", "content": PROMPT_SISTEMA_RAG + contexto}
        )

    for msg in mensagens.all():
        output.append({"role": msg.role.value, "content": msg.conteudo})
    return output
