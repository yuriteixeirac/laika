import asyncio
import logging
import os
import threading
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

logger = logging.getLogger(__name__)

DeepSeekClient = AsyncOpenAI(
    base_url="https://api.deepseek.com", api_key=os.getenv("DEEPSEEK_API_KEY")
)

MODELO_LLM = "deepseek-v4-flash"

# --- contrato de embedding --------------------------------------------------
# Trocar qualquer um destes valores invalida os vetores já gravados: é preciso
# reexecutar a ingestão, pois o retrieval filtra por `VERSAO_EMBEDDING`.
MODELO_EMBEDDING = "intfloat/multilingual-e5-base"
ESQUEMA_EMBEDDING = "e5-query-passage-v1"
VERSAO_EMBEDDING = f"{MODELO_EMBEDDING}::{ESQUEMA_EMBEDDING}"
# O E5 foi treinado com prefixos distintos para consulta e passagem.
E5_QUERY_PREFIX = "query: "
E5_PASSAGE_PREFIX = "passage: "

# --- retrieval --------------------------------------------------------------
# Quantidade de chunks recuperados do pgvector para montar o contexto do RAG.
RAG_TOP_K = 3
# Distância de cosseno máxima (1 - similaridade) para um chunk entrar no contexto.
# O E5 comprime as similaridades perto de 1; calibre com o conjunto de avaliação.
RAG_DISTANCIA_MAXIMA = float(os.getenv("RAG_DISTANCIA_MAXIMA", "0.40"))

PROMPT_SISTEMA_RAG = (
    "Você é o Laika, um assistente que responde perguntas com base na bibliografia "
    "do curso técnico em informática do IFRN campus Ceará-Mirim.\n"
    "Responda usando exclusivamente o contexto recuperado abaixo e cite o documento "
    "e a página (ex.: 'Nome do documento, p. 12') das informações que utilizar. "
    "Se o contexto não contiver a resposta, diga explicitamente que não encontrou "
    "essa informação na bibliografia e não invente.\n\n"
    "Contexto recuperado:\n"
)

PROMPT_CONDENSAO = (
    "Você reescreve a última pergunta do aluno como uma consulta de busca "
    "autônoma, em português, resolvendo pronomes e referências a partir do "
    "histórico da conversa. Responda APENAS com a consulta de busca autônoma, "
    "sem markdown e sem explicações."
)

SEM_CONTEXTO = "(nenhum trecho relevante encontrado na bibliografia)"

_embedding_model: Any = None
_embedding_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
def get_embedding_model() -> Any:
    """Carrega, uma única vez, o mesmo modelo utilizado na ingestão."""
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("carregando modelo de embedding %s", MODELO_EMBEDDING)
                _embedding_model = SentenceTransformer(MODELO_EMBEDDING)
    return _embedding_model


def _encode(textos: str | list[str]) -> Any:
    return get_embedding_model().encode(textos, normalize_embeddings=True)


def embed_passagens(textos: Sequence[str]) -> list[list[float]]:
    """Embeddings dos chunks, com o prefixo `passage:` do E5. Usado na ingestão."""
    return _encode([E5_PASSAGE_PREFIX + texto for texto in textos]).tolist()


async def embed_consulta(consulta: str) -> list[float]:
    """Embedding da pergunta, com o prefixo `query:` do E5, fora do event loop."""
    embedding = await asyncio.to_thread(_encode, E5_QUERY_PREFIX + consulta)
    return embedding.tolist()


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
async def recuperar_chunks(
    db: AsyncSession,
    consulta: str,
    limite: int = RAG_TOP_K,
    distancia_maxima: float = RAG_DISTANCIA_MAXIMA,
) -> Sequence[tuple[Chunk, str]]:
    """Busca no pgvector os `limite` chunks mais similares que passam do limiar."""
    embedding = await embed_consulta(consulta)
    distancia = Chunk.embedding.cosine_distance(embedding)

    stmt = (
        select(Chunk, Documento.nome)
        .join(Documento, Chunk.documento_id == Documento.id)
        .where(
            Chunk.versao_embedding == VERSAO_EMBEDDING,
            distancia < distancia_maxima,
        )
        .order_by(distancia)
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
    """Recupera os melhores chunks da consulta e monta o contexto."""
    resultados = await recuperar_chunks(db, consulta)

    if not resultados:
        logger.info(
            "nenhum chunk passou do limiar %.2f para a consulta %r",
            RAG_DISTANCIA_MAXIMA,
            consulta[:120],
        )

    return formatar_contexto(resultados)


# --------------------------------------------------------------------------- #
# Dependências e autenticação
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Mensagens e prompt
# --------------------------------------------------------------------------- #
async def gerar_titulo(input: str, output: str) -> str | None:
    res = await DeepSeekClient.chat.completions.create(
        model=MODELO_LLM,
        messages=[
            {
                "role": "user",
                "content": f"gera APENAS um titulo de sessão, seu output deve ser SÓ o título, sem markdown, baseado nessas mensagens\n\n{input, output}",
            }
        ],
    )
    return res.choices[0].message.content


async def get_session_messages(db: AsyncSession, sessao_id: int) -> list[dict]:
    """Histórico da sessão em ordem cronológica, no formato aceito pela LLM."""
    mensagens = await db.scalars(
        select(Mensagem)
        .where(Mensagem.sessao_id == sessao_id)
        .order_by(Mensagem.id)
    )

    return [
        {"role": msg.role.value, "content": msg.conteudo} for msg in mensagens.all()
    ]


def montar_mensagens(historico: Sequence[dict], contexto: str) -> list[dict]:
    """Prepende o prompt de sistema com o contexto ao histórico da sessão."""
    return [
        {"role": "system", "content": PROMPT_SISTEMA_RAG + contexto},
        *historico,
    ]


async def condensar_consulta(historico: Sequence[dict], pergunta: str) -> str:
    """Reescreve follow-ups ("e isso?") em uma consulta de busca autônoma.

    A pergunta atual é a última mensagem do histórico; sem mensagens anteriores
    não há o que resolver e nenhuma chamada extra é feita à LLM. Se a condensação
    falhar, a pergunta original é usada — o retrieval nunca fica sem consulta.
    """
    anteriores = list(historico)
    if anteriores and anteriores[-1].get("content") == pergunta:
        anteriores = anteriores[:-1]

    if not anteriores:
        return pergunta

    try:
        resposta = await DeepSeekClient.chat.completions.create(
            model=MODELO_LLM,
            messages=[
                {"role": "system", "content": PROMPT_CONDENSAO},
                *anteriores,
                {"role": "user", "content": pergunta},
                {"role": "user", "content": "Consulta de busca autônoma:"},
            ],
        )
    except Exception:
        logger.exception("falha ao condensar a consulta; usando a pergunta original")
        return pergunta

    consulta = (resposta.choices[0].message.content or "").strip()
    return consulta or pergunta
