"""Fixtures compartilhadas.

A suíte é hermética: nenhum teste abre conexão com PostgreSQL ou com a API da
DeepSeek. O ``AsyncSession`` é trocado por ``FakeSession`` (via
``dependency_overrides`` para o ``get_db`` e via monkeypatch para a sessão
secundária do chat) e o cliente OpenAI por ``FakeDeepSeek``.
"""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import (
    FakeDeepSeek,
    FakeSession,
    as_deepseek_client,
)

from app import app as fastapi_app  # noqa: E402  (depende do env de tests.helpers)
from app import utils
from app.models.chunk import Chunk
from app.models.usuario import Usuario


@pytest.fixture
def fake_db() -> FakeSession:
    return FakeSession()


@pytest.fixture
def usuario() -> Usuario:
    return Usuario(
        id=1, matricula="2024112345", nome="Fulana de Tal", email="fulana@ifrn.edu.br"
    )


@pytest.fixture
def autenticado(monkeypatch: pytest.MonkeyPatch, usuario: Usuario) -> Usuario:
    """Faz as rotas enxergarem um usuário logado sem passar pelo SUAP."""

    async def fake_get_current_user(request, db):
        return usuario

    monkeypatch.setattr(utils, "get_current_user", fake_get_current_user)
    return usuario


@pytest.fixture
def client(fake_db: FakeSession):
    async def override_get_db():
        yield fake_db

    fastapi_app.dependency_overrides[utils.get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def deepseek(monkeypatch: pytest.MonkeyPatch):
    """Instala um dublê do cliente DeepSeek e o devolve para inspeção."""

    def instalar(**kwargs) -> FakeDeepSeek:
        fake = FakeDeepSeek(**kwargs)
        monkeypatch.setattr(utils, "DeepSeekClient", as_deepseek_client(fake))
        return fake

    return instalar


@pytest.fixture
def embedding_fake(monkeypatch: pytest.MonkeyPatch):
    """Evita carregar o sentence-transformers durante os testes."""
    chamadas: list[str] = []

    async def fake_embed(consulta: str) -> list[float]:
        chamadas.append(consulta)
        return [0.0] * 768

    monkeypatch.setattr(utils, "embed_consulta", fake_embed)
    return chamadas


@pytest.fixture
def chunk() -> Chunk:
    return Chunk(
        id=1,
        conteudo="Um laço de repetição executa um bloco enquanto a condição for verdadeira.",
        pagina=12,
        documento_id=1,
    )
