"""Testes dos endpoints de ``app/routers/auth_router.py``."""

from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app import oauth
from tests.helpers import FakeSession

DADOS_SUAP = {
    "identificacao": "2024112345",
    "nome_social": "Fulana de Tal",
    "nome_registro": "Fulano de Tal",
    "email_preferencial": "fulana@ifrn.edu.br",
}


def _fingir_suap(monkeypatch, *, dados=DADOS_SUAP, status_code=200):
    async def authorize_access_token(request, **kwargs):
        return {"access_token": "token-de-teste"}

    async def get(url, token=None, **kwargs):
        return SimpleNamespace(status_code=status_code, json=lambda: dados)

    monkeypatch.setattr(oauth.suap, "authorize_access_token", authorize_access_token)
    monkeypatch.setattr(oauth.suap, "get", get)


# --------------------------------------------------------------------------- #
# GET /auth/suap/login
# --------------------------------------------------------------------------- #


def test_login_redireciona_para_o_suap(client, monkeypatch):
    async def authorize_redirect(request, redirect_uri=None, **kwargs):
        return RedirectResponse(
            url="https://suap.ifrn.edu.br/o/authorize/?state=abc", status_code=302
        )

    monkeypatch.setattr(oauth.suap, "authorize_redirect", authorize_redirect)

    resposta = client.get("/auth/suap/login", follow_redirects=False)

    assert resposta.status_code == 302
    assert "suap.ifrn.edu.br" in resposta.headers["location"]


# --------------------------------------------------------------------------- #
# GET /auth/suap/callback
# --------------------------------------------------------------------------- #


def test_callback_cria_usuario_novo(client, fake_db: FakeSession, monkeypatch):
    _fingir_suap(monkeypatch)
    fake_db.scalar_result = None  # matrícula ainda não cadastrada

    resposta = client.get("/auth/suap/callback")

    assert resposta.status_code == 200
    assert resposta.json()["msg"] == "login realizado com sucesso!"

    usuario = fake_db.added[-1]
    assert usuario.matricula == DADOS_SUAP["identificacao"]
    assert usuario.nome == DADOS_SUAP["nome_social"]
    assert usuario.email == DADOS_SUAP["email_preferencial"]
    assert usuario.id is not None
    assert fake_db.refreshed == [usuario]
    assert fake_db.commits == 1


def test_callback_atualiza_usuario_existente(
    client, fake_db: FakeSession, monkeypatch, usuario
):
    _fingir_suap(monkeypatch, dados={**DADOS_SUAP, "nome_social": None})
    fake_db.scalar_result = usuario

    resposta = client.get("/auth/suap/callback")

    assert resposta.status_code == 200
    # Cai no fallback `nome_registro` e reaproveita o mesmo registro.
    assert usuario.nome == DADOS_SUAP["nome_registro"]
    assert usuario in fake_db.added
    assert len([o for o in fake_db.added if type(o).__name__ == "Usuario"]) == 1


def test_callback_grava_user_id_na_sessao(
    client, fake_db: FakeSession, monkeypatch, usuario
):
    _fingir_suap(monkeypatch)
    fake_db.scalar_result = usuario

    assert client.get("/auth/suap/callback").status_code == 200

    # Com o cookie de sessão, as rotas protegidas passam a autenticar.
    fake_db.scalars_rows = []
    resposta = client.get("/sessao/")

    assert resposta.status_code == 200


def test_callback_erro_do_suap(client, fake_db: FakeSession, monkeypatch):
    _fingir_suap(monkeypatch, status_code=500)

    resposta = client.get("/auth/suap/callback")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "erro de requisição ao suap!"
    assert fake_db.added == []


# --------------------------------------------------------------------------- #
# POST /auth/logout
# --------------------------------------------------------------------------- #


def test_logout(client):
    resposta = client.post("/auth/logout")

    assert resposta.status_code == 200
    assert resposta.json()["msg"] == "logout realizado com sucesso!"


def test_logout_encerra_a_sessao(client, fake_db: FakeSession, monkeypatch, usuario):
    _fingir_suap(monkeypatch)
    fake_db.scalar_result = usuario
    client.get("/auth/suap/callback")

    assert client.post("/auth/logout").status_code == 200
    assert client.get("/sessao/").status_code == 401
