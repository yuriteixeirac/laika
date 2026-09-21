"""Testes de ``app/utils.py``."""

import sys
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app import utils
from app.models.mensagem import Role
from app.models.usuario import Usuario
from tests.helpers import FakeSession


# --------------------------------------------------------------------------- #
# get_db / get_current_user
# --------------------------------------------------------------------------- #


async def test_get_db_entrega_uma_async_session():
    gerador = utils.get_db()

    sessao = await gerador.__anext__()

    assert isinstance(sessao, AsyncSession)
    await gerador.aclose()


async def test_get_current_user_sem_login_retorna_401():
    request = SimpleNamespace(session={})

    with pytest.raises(HTTPException) as exc:
        await utils.get_current_user(request, FakeSession())

    assert exc.value.status_code == 401
    assert exc.value.detail == "usuário não logado."


async def test_get_current_user_inexistente_retorna_404():
    request = SimpleNamespace(session={"user_id": "42"})
    db = FakeSession(scalar=None)

    with pytest.raises(HTTPException) as exc:
        await utils.get_current_user(request, db)

    assert exc.value.status_code == 404
    assert exc.value.detail == "usuário não existente."


async def test_get_current_user_logado(usuario: Usuario):
    request = SimpleNamespace(session={"user_id": str(usuario.id)})
    db = FakeSession(scalar=usuario)

    resultado = await utils.get_current_user(request, db)

    assert resultado is usuario
    # A busca foi feita pelo id da sessão.
    sql = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "usuario.id" in sql


# --------------------------------------------------------------------------- #
# gerar_titulo
# --------------------------------------------------------------------------- #


async def test_gerar_titulo_usa_a_resposta_da_llm(deepseek):
    llm = deepseek(titulo="Laços de repetição")

    titulo = await utils.gerar_titulo("o que é um laço?", "um laço repete...")

    assert titulo == "Laços de repetição"
    assert len(llm.chamadas) == 1
    prompt = llm.chamadas[0]["messages"][0]["content"]
    assert "o que é um laço?" in prompt
    assert "um laço repete..." in prompt


# --------------------------------------------------------------------------- #
# get_session_messages
# --------------------------------------------------------------------------- #


async def test_get_session_messages_sem_contexto_preserva_historico(fake_db: FakeSession):
    fake_db.scalars_rows = [
        SimpleNamespace(role=Role.USER, conteudo="oi"),
        SimpleNamespace(role=Role.ASSISTANT, conteudo="olá"),
    ]

    mensagens = await utils.get_session_messages(fake_db, sessao_id=1)

    assert mensagens == [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "olá"},
    ]
    sql = str(fake_db.statements[0].compile(dialect=postgresql.dialect()))
    assert "ORDER BY mensagem.id" in sql


async def test_get_session_messages_com_contexto_prepende_system(fake_db: FakeSession):
    fake_db.scalars_rows = [SimpleNamespace(role=Role.USER, conteudo="pergunta")]

    mensagens = await utils.get_session_messages(fake_db, sessao_id=1, contexto="CTX")

    assert mensagens[0]["role"] == "system"
    assert mensagens[0]["content"] == utils.PROMPT_SISTEMA_RAG + "CTX"
    assert mensagens[1] == {"role": "user", "content": "pergunta"}


# --------------------------------------------------------------------------- #
# formatação do contexto
# --------------------------------------------------------------------------- #


def test_formatar_contexto_vazio_usa_aviso_explicito():
    assert utils.formatar_contexto([]) == utils.SEM_CONTEXTO


def test_formatar_contexto_numera_e_cita_documento_e_pagina():
    resultados = [
        (SimpleNamespace(pagina=3, conteudo="trecho A"), "Doc A"),
        (SimpleNamespace(pagina=10, conteudo="trecho B"), "Doc B"),
    ]

    texto = utils.formatar_contexto(resultados)

    assert "[1] Doc A (página 3):" in texto
    assert "[2] Doc B (página 10):" in texto
    assert texto.index("[1]") < texto.index("[2]")
    assert "trecho A" in texto and "trecho B" in texto


# --------------------------------------------------------------------------- #
# retrieval
# --------------------------------------------------------------------------- #


def _limite(stmt) -> int:
    return stmt._limit_clause.value


async def test_recuperar_chunks_consulta_pgvector_com_cosseno(
    fake_db: FakeSession, monkeypatch, chunk, embedding_fake
):
    fake_db.execute_rows = [(chunk, "Algoritmos")]

    resultados = await utils.recuperar_chunks(fake_db, "o que é um laço?")

    assert resultados == [(chunk, "Algoritmos")]
    assert embedding_fake == ["o que é um laço?"]

    stmt = fake_db.statements[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "<=>" in sql  # distância de cosseno do pgvector
    assert "JOIN documento" in sql
    assert _limite(stmt) == utils.RAG_TOP_K == 3


async def test_recuperar_chunks_respeita_limite_customizado(
    fake_db: FakeSession, embedding_fake
):
    fake_db.execute_rows = []

    await utils.recuperar_chunks(fake_db, "consulta", limite=7)

    assert _limite(fake_db.statements[0]) == 7


async def test_recuperar_contexto_formata_os_chunks(
    fake_db: FakeSession, chunk, embedding_fake
):
    fake_db.execute_rows = [(chunk, "Algoritmos")]

    contexto = await utils.recuperar_contexto(fake_db, "o que é um laço?")

    assert "Algoritmos (página 12)" in contexto
    assert "laço de repetição" in contexto


async def test_recuperar_contexto_sem_resultados(fake_db: FakeSession, embedding_fake):
    fake_db.execute_rows = []

    assert await utils.recuperar_contexto(fake_db, "fora do corpus") == utils.SEM_CONTEXTO


# --------------------------------------------------------------------------- #
# embeddings
# --------------------------------------------------------------------------- #


def test_get_embedding_model_e_singleton(monkeypatch):
    criados: list[str] = []

    class FakeSentenceTransformer:
        def __init__(self, nome: str):
            criados.append(nome)

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    monkeypatch.setattr(utils, "_embedding_model", None)

    primeiro = utils.get_embedding_model()
    segundo = utils.get_embedding_model()

    assert primeiro is segundo
    assert criados == ["intfloat/multilingual-e5-base"]


async def test_embed_texto_normaliza_em_outra_thread(monkeypatch):
    capturado = {}

    class FakeEmbedding:
        def tolist(self) -> list[float]:
            return [0.1, 0.2]

    class FakeModel:
        def encode(self, texto, normalize_embeddings=False):
            capturado["texto"] = texto
            capturado["normalize_embeddings"] = normalize_embeddings
            capturado["thread"] = threading.get_ident()
            return FakeEmbedding()

    monkeypatch.setattr(utils, "get_embedding_model", lambda: FakeModel())

    embedding = await utils.embed_texto("consulta")

    assert embedding == [0.1, 0.2]
    assert capturado["texto"] == "consulta"
    assert capturado["normalize_embeddings"] is True
    # Não pode bloquear o event loop.
    assert capturado["thread"] != threading.get_ident()
