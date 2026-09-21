"""Testes de ``scripts/ingestion.py``.

A ingestão é testada sem PDFs reais, sem modelo de embedding e sem banco.
"""

from types import SimpleNamespace

import pytest

from app import utils
from app.models import Chunk, Documento
from scripts import ingestion
from tests.helpers import FakeSession


@pytest.fixture
def pdf_fake(tmp_path) -> str:
    caminho = tmp_path / "logica.pdf"
    caminho.write_bytes(b"%PDF-1.4 conteudo")
    return str(caminho)


# --------------------------------------------------------------------------- #
# helpers de leitura
# --------------------------------------------------------------------------- #


def test_hash_arquivo_e_estavel_e_sensivel_ao_conteudo(tmp_path):
    arquivo = tmp_path / "doc.pdf"
    arquivo.write_bytes(b"conteudo A")

    primeiro = ingestion.hash_arquivo(str(arquivo))

    assert primeiro == ingestion.hash_arquivo(str(arquivo))
    assert len(primeiro) == 64

    arquivo.write_bytes(b"conteudo B")
    assert ingestion.hash_arquivo(str(arquivo)) != primeiro


def test_normalizar_nome():
    assert ingestion.normalizar_nome("logica-de-programacao.pdf") == (
        "Logica De Programacao"
    )


def test_chunk_page_gera_janelas_com_overlap():
    paginas = ingestion.chunk_page("x" * 1000)

    assert len(paginas) == 4  # janelas em 0, 300, 600 e 900
    assert len(paginas[0]) == 350  # 300 + 50 do overlap seguinte
    assert len(paginas[1]) == 400  # 50 anteriores + 300 + 50 seguintes
    assert all(pagina == "x" * len(pagina) for pagina in paginas)


# --------------------------------------------------------------------------- #
# ingerir_arquivo
# --------------------------------------------------------------------------- #


async def test_ingerir_arquivo_grava_hash_e_versao_do_embedding(
    monkeypatch, fake_db: FakeSession, pdf_fake
):
    monkeypatch.setattr(ingestion, "hash_arquivo", lambda caminho: "hash-fake")
    monkeypatch.setattr(
        ingestion, "extrair_paginas", lambda caminho: [(0, ["a", "b"]), (1, ["c"])]
    )
    embed_chamadas: list = []
    monkeypatch.setattr(
        utils,
        "embed_passagens",
        lambda textos: embed_chamadas.append(textos) or [[0.0] * 768 for _ in textos],
    )
    fake_db.scalar_result = None  # documento ainda não existe

    ingerido = await ingestion.ingerir_arquivo(fake_db, pdf_fake)

    assert ingerido is True

    documento = next(obj for obj in fake_db.added if isinstance(obj, Documento))
    assert documento.hash == "hash-fake"
    assert documento.nome == "Logica"

    chunks = [obj for obj in fake_db.added if isinstance(obj, Chunk)]
    assert [c.pagina for c in chunks] == [0, 0, 1]
    assert [c.versao_embedding for c in chunks] == [utils.VERSAO_EMBEDDING] * 3
    assert [c.conteudo for c in chunks] == ["a", "b", "c"]

    # As passagens foram embedadas de uma vez só.
    assert embed_chamadas == [["a", "b", "c"]]
    assert fake_db.commits == 1


async def test_ingerir_arquivo_pula_duplicado(monkeypatch, fake_db: FakeSession, pdf_fake):
    existente = Documento(id=1, nome="Logica", hash="hash-fake")
    fake_db.scalar_result = existente
    monkeypatch.setattr(ingestion, "hash_arquivo", lambda caminho: "hash-fake")
    extraidas: list = []
    monkeypatch.setattr(
        ingestion, "extrair_paginas", lambda caminho: extraidas.append(caminho) or []
    )

    ingerido = await ingestion.ingerir_arquivo(fake_db, pdf_fake)

    assert ingerido is False
    assert fake_db.added == []
    assert extraidas == []  # nem chegou a abrir o PDF
    assert fake_db.commits == 0


async def test_ingerir_arquivo_com_forcar_apaga_chunks_antigos(
    monkeypatch, fake_db: FakeSession, pdf_fake
):
    existente = Documento(id=1, nome="Logica", hash="hash-fake")
    fake_db.scalar_result = existente
    monkeypatch.setattr(ingestion, "hash_arquivo", lambda caminho: "hash-fake")
    monkeypatch.setattr(ingestion, "extrair_paginas", lambda caminho: [(0, ["a"])])
    monkeypatch.setattr(
        utils, "embed_passagens", lambda textos: [[0.0] * 768 for _ in textos]
    )

    ingerido = await ingestion.ingerir_arquivo(fake_db, pdf_fake, forcar=True)

    assert ingerido is True
    assert fake_db.deleted == [existente]
    assert any("DELETE FROM chunk" in str(stmt) for stmt in fake_db.statements)
    assert fake_db.commits == 1


async def test_ingerir_arquivo_sem_texto_nao_carrega_o_modelo(
    monkeypatch, fake_db: FakeSession, pdf_fake
):
    monkeypatch.setattr(ingestion, "hash_arquivo", lambda caminho: "hash-vazio")
    monkeypatch.setattr(ingestion, "extrair_paginas", lambda caminho: [(0, [])])
    chamadas: list = []
    monkeypatch.setattr(
        utils, "embed_passagens", lambda textos: chamadas.append(textos)
    )
    fake_db.scalar_result = None

    ingerido = await ingestion.ingerir_arquivo(fake_db, pdf_fake)

    assert ingerido is True
    assert chamadas == []
    assert [obj for obj in fake_db.added if isinstance(obj, Chunk)] == []


# --------------------------------------------------------------------------- #
# ingest
# --------------------------------------------------------------------------- #


async def test_ingest_continua_apos_falha_e_conta_os_erros(
    monkeypatch, tmp_path, fake_db: FakeSession
):
    (tmp_path / "ok.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "ruim.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(ingestion, "PASTA_PDF", str(tmp_path))

    async def dispose():
        return None

    monkeypatch.setattr(ingestion, "AsyncSession", lambda engine: fake_db)
    monkeypatch.setattr(ingestion, "engine", SimpleNamespace(dispose=dispose))

    ingeridos: list[str] = []

    async def ingerir_arquivo(db, caminho, *, forcar=False):
        if caminho.endswith("ruim.pdf"):
            raise RuntimeError("PDF corrompido")
        ingeridos.append(caminho)
        return True

    monkeypatch.setattr(ingestion, "ingerir_arquivo", ingerir_arquivo)

    falhas = await ingestion.ingest()

    assert falhas == 1
    assert fake_db.rollbacks == 1
    # O arquivo seguinte foi processado mesmo com a falha anterior.
    assert [caminho.rsplit("/", 1)[-1] for caminho in ingeridos] == ["ok.pdf"]


async def test_ingest_falha_quando_a_pasta_nao_existe(monkeypatch, tmp_path):
    monkeypatch.setattr(ingestion, "PASTA_PDF", str(tmp_path / "nao-existe"))

    with pytest.raises(FileNotFoundError):
        await ingestion.ingest()


async def test_ingest_sem_pdfs_nao_falha(monkeypatch, tmp_path):
    monkeypatch.setattr(ingestion, "PASTA_PDF", str(tmp_path))

    assert await ingestion.ingest() == 0
