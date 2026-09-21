"""Duplos de teste e utilitários compartilhados.

Este módulo é importado antes de qualquer módulo da aplicação (é importado pelo
`conftest.py`), por isso ele configura as variáveis de ambiente de que
`app/__init__.py` depende no momento do import.
"""

import os

os.environ.setdefault("SECRET_KEY", "chave-de-teste")
os.environ.setdefault(
    "SQLALCHEMY_DATABASE_URI",
    "postgresql+asyncpg://teste:teste@localhost:5432/teste",
)
os.environ.setdefault("SUAP_CLIENT_ID", "client-id-de-teste")
os.environ.setdefault("SUAP_CLIENT_SECRET", "client-secret-de-teste")
os.environ.setdefault("DEEPSEEK_API_KEY", "chave-deepseek-de-teste")

import json
from types import SimpleNamespace
from typing import Any

from app.models.mensagem import Mensagem

# --------------------------------------------------------------------------- #
# Duplo de AsyncSession
# --------------------------------------------------------------------------- #


class FakeResult:
    """Duplo de ``Result``/``ScalarResult`` do SQLAlchemy."""

    def __init__(self, rows: list[Any]):
        self._rows = list(rows)

    def all(self) -> list[Any]:
        return self._rows

    def scalars(self) -> "FakeResult":
        return self

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    """Duplo de ``AsyncSession``.

    Implementa apenas a superfície usada pelos routers e pelo ``utils``: cada
    método registra a chamada e devolve dados roteirizados pelo teste, sem nunca
    tocar em PostgreSQL/asyncpg.
    """

    def __init__(
        self,
        scalar: Any = None,
        scalars_rows: list[Any] | None = None,
        execute_rows: list[Any] | None = None,
    ):
        self.scalar_result = scalar
        self.scalars_rows = scalars_rows
        self.execute_rows = list(execute_rows) if execute_rows is not None else []
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.refreshed: list[Any] = []
        self.statements: list[Any] = []
        self.commits = 0
        self.flushes = 0
        self.rollbacks = 0
        self._next_id = 1

    # -- escrita -----------------------------------------------------------
    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1
        for obj in self.added:
            self._atribuir_id(obj)

    async def commit(self) -> None:
        self.commits += 1
        for obj in self.added:
            self._atribuir_id(obj)

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, obj: Any) -> None:
        self.refreshed.append(obj)
        self._atribuir_id(obj)

    async def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    async def get(self, model: type, pk: Any) -> Any:
        for obj in self.added:
            if isinstance(obj, model) and getattr(obj, "id", None) == pk:
                return obj
        if isinstance(self.scalar_result, model):
            return self.scalar_result
        return None

    # -- leitura -----------------------------------------------------------
    async def scalar(self, stmt: Any) -> Any:
        self.statements.append(stmt)
        return self.scalar_result

    async def scalars(self, stmt: Any) -> FakeResult:
        self.statements.append(stmt)
        if self.scalars_rows is not None:
            return FakeResult(self.scalars_rows)
        # Sem roteiro explícito, devolve o que foi adicionado à sessão (útil
        # para o histórico montado dentro dos próprios endpoints de chat).
        return FakeResult([obj for obj in self.added if isinstance(obj, Mensagem)])

    async def execute(self, stmt: Any) -> FakeResult:
        self.statements.append(stmt)
        return FakeResult(self.execute_rows)

    # -- contexto assíncrono ----------------------------------------------
    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False

    # -- auxiliares --------------------------------------------------------
    def _atribuir_id(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = self._next_id
            self._next_id += 1

    def mensagens(self, role: Any = None) -> list[Any]:
        """Mensagens que passaram por ``add`` (opcionalmente de um ``role``)."""
        return [
            obj
            for obj in self.added
            if isinstance(obj, Mensagem) and (role is None or obj.role == role)
        ]


# --------------------------------------------------------------------------- #
# Duplo do cliente DeepSeek
# --------------------------------------------------------------------------- #


class FakeDeepSeek:
    """Dublê do ``AsyncOpenAI``.

    Grava cada chamada em ``chamadas`` e, quando ``stream=True``, devolve um
    gerador assíncrono com os deltas configurados.
    """

    def __init__(
        self,
        deltas: tuple[str, ...] = ("Olá", ", mundo"),
        titulo: str = "Título gerado",
        erro: Exception | None = None,
    ):
        self.deltas = list(deltas)
        self.titulo = titulo
        self.erro = erro
        self.chamadas: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.chamadas.append(kwargs)

        if self.erro is not None:
            raise self.erro

        if not kwargs.get("stream"):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=self.titulo))
                ]
            )

        async def gerador():
            for delta in self.deltas:
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=delta))]
                )

        return gerador()

    @property
    def chamada_stream(self) -> dict[str, Any]:
        return next(c for c in self.chamadas if c.get("stream"))

    @property
    def mensagens_enviadas(self) -> list[dict[str, Any]]:
        return self.chamada_stream["messages"]


def as_deepseek_client(fake: FakeDeepSeek) -> SimpleNamespace:
    """Envolve o dublê na mesma forma de ``utils.DeepSeekClient``."""
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake.create))
    )


# --------------------------------------------------------------------------- #
# SSE
# --------------------------------------------------------------------------- #


def parse_sse(texto: str) -> list[tuple[str | None, Any]]:
    """Converte o corpo SSE em ``[(evento, data), ...]``.

    Eventos sem linha ``event:`` (os deltas de chat) vêm com evento ``None``.
    """
    eventos: list[tuple[str | None, Any]] = []
    for bloco in texto.strip().split("\n\n"):
        if not bloco.strip():
            continue
        evento: str | None = None
        dados: Any = None
        for linha in bloco.splitlines():
            if linha.startswith("event: "):
                evento = linha.removeprefix("event: ")
            elif linha.startswith("data: "):
                dados = json.loads(linha.removeprefix("data: "))
        eventos.append((evento, dados))
    return eventos


def deltas_sse(eventos: list[tuple[str | None, Any]]) -> str:
    """Concatena os deltas de uma resposta SSE."""
    return "".join(
        dados["delta"]
        for evento, dados in eventos
        if evento is None and dados and "delta" in dados
    )
