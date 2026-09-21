"""Testes dos endpoints de ``app/routers/sessao_router.py``."""

from types import SimpleNamespace

from app.models.sessao import Sessao
from tests.helpers import FakeSession


def test_listar_sessoes(client, fake_db: FakeSession, autenticado):
    fake_db.scalars_rows = [
        Sessao(id=1, titulo="Primeira", usuario_id=autenticado.id),
        Sessao(id=2, titulo="Segunda", usuario_id=autenticado.id),
    ]

    resposta = client.get("/sessao/")

    assert resposta.status_code == 200
    assert [s["titulo"] for s in resposta.json()] == ["Primeira", "Segunda"]


def test_obter_sessao(client, fake_db: FakeSession, autenticado):
    fake_db.scalar_result = Sessao(id=1, titulo="Minha sessão", usuario_id=autenticado.id)

    resposta = client.get("/sessao/1")

    assert resposta.status_code == 200
    assert resposta.json()["titulo"] == "Minha sessão"


def test_obter_sessao_inexistente(client, fake_db: FakeSession, autenticado):
    fake_db.scalar_result = None

    resposta = client.get("/sessao/1")

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "sessão não existente."


def test_atualizar_sessao(client, fake_db: FakeSession, autenticado):
    sessao = Sessao(id=1, titulo="Antiga", usuario_id=autenticado.id)
    fake_db.scalar_result = sessao

    resposta = client.put("/sessao/1", json={"titulo": "Nova"})

    assert resposta.status_code == 200
    assert sessao.titulo == "Nova"
    assert sessao in fake_db.added
    assert fake_db.commits == 1


def test_atualizar_sessao_inexistente(client, fake_db: FakeSession, autenticado):
    fake_db.scalar_result = None

    resposta = client.put("/sessao/1", json={"titulo": "Nova"})

    assert resposta.status_code == 404
    assert fake_db.commits == 0


def test_deletar_sessao(client, fake_db: FakeSession, autenticado):
    sessao = Sessao(id=1, titulo="Antiga", usuario_id=autenticado.id)
    fake_db.scalar_result = sessao

    resposta = client.delete("/sessao/1")

    assert resposta.status_code == 200
    assert fake_db.deleted == [sessao]
    assert fake_db.commits == 1


def test_deletar_sessao_inexistente(client, fake_db: FakeSession, autenticado):
    fake_db.scalar_result = None

    resposta = client.delete("/sessao/1")

    assert resposta.status_code == 404
    assert fake_db.deleted == []


def test_listar_mensagens_da_sessao(client, fake_db: FakeSession, autenticado):
    fake_db.scalar_result = SimpleNamespace(
        id=1,
        mensagens=[
            {"id": 1, "conteudo": "oi", "role": "user"},
            {"id": 2, "conteudo": "olá", "role": "assistant"},
        ],
    )

    resposta = client.get("/sessao/1/mensagens")

    assert resposta.status_code == 200
    assert [m["conteudo"] for m in resposta.json()] == ["oi", "olá"]


def test_listar_mensagens_sessao_inexistente(client, fake_db: FakeSession, autenticado):
    fake_db.scalar_result = None

    resposta = client.get("/sessao/1/mensagens")

    assert resposta.status_code == 404


def test_rotas_de_sessao_exigem_login(client, fake_db: FakeSession):
    # Sem a fixture `autenticado`, o `utils.get_current_user` real é usado.
    resposta = client.get("/sessao/")

    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "usuário não logado."
    assert fake_db.statements == []
