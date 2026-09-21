"""Testes dos endpoints de ``app/routers/chat_router.py``."""

from types import SimpleNamespace

import pytest

from app import utils
from app.models.mensagem import Role
from app.models.sessao import Sessao
from app.routers import chat_router
from tests.helpers import FakeSession, deltas_sse, parse_sse


@pytest.fixture
def sessao_secundaria(monkeypatch: pytest.MonkeyPatch, fake_db: FakeSession):
    """A sessão aberta dentro do stream (``AsyncSession(engine)``) também é o duplo."""
    monkeypatch.setattr(chat_router, "AsyncSession", lambda engine: fake_db)
    return fake_db


# --------------------------------------------------------------------------- #
# POST /chat/
# --------------------------------------------------------------------------- #


def test_start_chat_faz_retrieval_e_streaming(
    client,
    fake_db: FakeSession,
    autenticado,
    deepseek,
    embedding_fake,
    chunk,
    sessao_secundaria,
):
    fake_db.execute_rows = [(chunk, "Algoritmos e Lógica de Programação")]
    llm = deepseek(deltas=["Olá", ", ", "mundo"], titulo="Laços de repetição")

    resposta = client.post("/chat/", json={"conteudo": "o que é um laço?"})

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/event-stream")

    eventos = parse_sse(resposta.text)
    assert eventos[0][0] == "meta"
    assert eventos[0][1]["redirect"] == f"/chat/{eventos[0][1]['session_id']}"
    assert deltas_sse(eventos) == "Olá, mundo"
    assert eventos[-1][0] == "done"
    assert eventos[-1][1]["title"] == "Laços de repetição"

    # O embedding da consulta do usuário alimentou o retrieval.
    assert embedding_fake == ["o que é um laço?"]


def test_start_chat_prompt_recebe_o_contexto_recuperado(
    client, fake_db: FakeSession, autenticado, deepseek, embedding_fake, chunk, sessao_secundaria
):
    fake_db.execute_rows = [(chunk, "Algoritmos e Lógica de Programação")]
    llm = deepseek()

    client.post("/chat/", json={"conteudo": "o que é um laço?"})

    sistema = llm.mensagens_enviadas[0]
    assert sistema["role"] == "system"
    assert sistema["content"].startswith(utils.PROMPT_SISTEMA_RAG)
    assert "Algoritmos e Lógica de Programação (página 12)" in sistema["content"]
    assert "Um laço de repetição executa" in sistema["content"]
    assert [m["role"] for m in llm.mensagens_enviadas[1:]] == ["user"]
    assert llm.chamada_stream["model"] == "deepseek-v4-flash"


def test_start_chat_persiste_sessao_mensagens_e_titulo(
    client, fake_db: FakeSession, autenticado, deepseek, embedding_fake, chunk, sessao_secundaria
):
    fake_db.execute_rows = [(chunk, "Algoritmos")]
    deepseek(deltas=["Olá", " mundo"], titulo="Laços de repetição")

    client.post("/chat/", json={"conteudo": "o que é um laço?"})

    sessoes = [obj for obj in fake_db.added if isinstance(obj, Sessao)]
    assert len(sessoes) == 1
    assert sessoes[0].titulo == "Laços de repetição"
    assert sessoes[0].usuario_id == autenticado.id

    assert [m.conteudo for m in fake_db.mensagens(Role.USER)] == ["o que é um laço?"]
    assert [m.conteudo for m in fake_db.mensagens(Role.ASSISTANT)] == ["Olá mundo"]
    assert fake_db.mensagens(Role.ASSISTANT)[0].sessao_id == sessoes[0].id
    assert fake_db.commits >= 2


def test_start_chat_sem_chunks_avisa_no_prompt(
    client, fake_db: FakeSession, autenticado, deepseek, embedding_fake, sessao_secundaria
):
    fake_db.execute_rows = []
    llm = deepseek(deltas=[], titulo="Título")

    resposta = client.post("/chat/", json={"conteudo": "pergunta fora do corpus"})

    assert resposta.status_code == 200
    assert utils.SEM_CONTEXTO in llm.mensagens_enviadas[0]["content"]
    assert deltas_sse(parse_sse(resposta.text)) == ""
    assert parse_sse(resposta.text)[-1] == ("done", {"title": "Título"})


def test_start_chat_persiste_saida_parcial_quando_a_llm_falha(
    client,
    fake_db: FakeSession,
    autenticado,
    monkeypatch: pytest.MonkeyPatch,
    embedding_fake,
    sessao_secundaria,
):
    async def create(**kwargs):
        if not kwargs.get("stream"):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="título"))]
            )

        async def gerador():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="parcial"))]
            )
            raise RuntimeError("conexão caiu")

        return gerador()

    monkeypatch.setattr(
        utils,
        "DeepSeekClient",
        SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    fake_db.execute_rows = []

    with pytest.raises(RuntimeError, match="conexão caiu"):
        client.post("/chat/", json={"conteudo": "pergunta"})

    # O bloco `finally` do endpoint persiste o que já foi streamado.
    assert [m.conteudo for m in fake_db.mensagens(Role.ASSISTANT)] == ["parcial"]


# --------------------------------------------------------------------------- #
# POST /chat/{sessao_id}
# --------------------------------------------------------------------------- #


def test_post_mensagem_sessao_inexistente(client, fake_db: FakeSession, autenticado):
    fake_db.scalar_result = None

    resposta = client.post("/chat/999", json={"conteudo": "oi"})

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Sessão não encontrada."
    assert fake_db.mensagens() == []


def test_post_mensagem_usa_historico_e_contexto(
    client, fake_db: FakeSession, autenticado, deepseek, embedding_fake, chunk, sessao_secundaria
):
    fake_db.scalar_result = Sessao(id=7, titulo="Sessão antiga", usuario_id=autenticado.id)
    fake_db.scalars_rows = [
        SimpleNamespace(role=Role.USER, conteudo="primeira pergunta"),
        SimpleNamespace(role=Role.ASSISTANT, conteudo="primeira resposta"),
        SimpleNamespace(role=Role.USER, conteudo="segunda pergunta"),
    ]
    fake_db.execute_rows = [(chunk, "Algoritmos")]
    llm = deepseek(deltas=["Certo"], titulo="título novo")

    resposta = client.post("/chat/7", json={"conteudo": "segunda pergunta"})

    assert resposta.status_code == 200
    eventos = parse_sse(resposta.text)
    assert eventos[0] == ("meta", None)
    assert deltas_sse(eventos) == "Certo"
    assert eventos[-1] == ("done", None)

    assert [m["role"] for m in llm.mensagens_enviadas] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert "Algoritmos (página 12)" in llm.mensagens_enviadas[0]["content"]

    persistidas = fake_db.mensagens(Role.ASSISTANT)
    assert [m.conteudo for m in persistidas] == ["Certo"]
    assert persistidas[0].sessao_id == 7
    assert [m.conteudo for m in fake_db.mensagens(Role.USER)] == ["segunda pergunta"]
