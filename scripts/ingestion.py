"""Ingestão dos PDFs de ``data/raw/`` no PostgreSQL.

Uso:
    uv run python -m scripts.ingestion [--force]

O ``--force`` re-ingere PDFs cujo hash já está no banco (apaga os chunks antigos
antes). Sem ele, arquivos já ingeridos são pulados.
"""

import argparse
import asyncio
import hashlib
import logging
import os

import pymupdf
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine, utils
from app.models import Chunk, Documento

logger = logging.getLogger(__name__)

PASTA_PDF = "data/raw/"


def chunk_page(page: str, size: int = 300, overlap: int = 50) -> list[str]:
    """Pega o conteúdo de uma página e retorna em chunks cujo tamanho é `size` + `overlap` * 2"""
    chunks = []
    for i in range(0, len(page), size):
        chunk = page[i : i + size]
        if i != 0:
            chunk = page[i - overlap : i] + chunk
        if i + overlap < len(page):
            chunk += page[i + size : i + size + overlap]
        chunks.append(chunk)
    return chunks


def normalizar_nome(nome: str) -> str:
    return nome.replace(".pdf", "").replace("-", " ").title()


def hash_arquivo(caminho: str) -> str:
    """SHA-256 do PDF, usado para não ingerir o mesmo arquivo duas vezes."""
    digest = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def extrair_paginas(caminho: str) -> list[tuple[int, list[str]]]:
    """Texto de cada página do PDF, já dividido em chunks."""
    with pymupdf.open(caminho) as pdf:
        return [(page.number, chunk_page(page.get_text())) for page in pdf]


async def ingerir_arquivo(
    db: AsyncSession, caminho: str, *, forcar: bool = False
) -> bool:
    """Ingere um PDF. Retorna ``False`` quando ele é pulado por já estar ingerido."""
    digest = hash_arquivo(caminho)
    nome = normalizar_nome(os.path.basename(caminho))

    existente = await db.scalar(select(Documento).where(Documento.hash == digest))
    if existente is not None:
        if not forcar:
            logger.info("%s já ingerido (hash %s); pulando.", nome, digest[:12])
            return False

        logger.info("re-ingerindo %s (--force).", nome)
        await db.execute(sa.delete(Chunk).where(Chunk.documento_id == existente.id))
        await db.delete(existente)
        await db.flush()

    itens = [
        (pagina, texto)
        for pagina, textos in extrair_paginas(caminho)
        for texto in textos
    ]
    if not itens:
        logger.warning("%s: nenhum texto extraído (PDF escaneado?).", nome)

    documento = Documento(nome=nome, hash=digest)
    db.add(documento)

    embeddings: list[list[float]] = []
    if itens:
        embeddings = await asyncio.to_thread(
            utils.embed_passagens, [texto for _, texto in itens]
        )

    for (pagina, texto), embedding in zip(itens, embeddings):
        db.add(
            Chunk(
                conteudo=texto,
                embedding=embedding,
                pagina=pagina,
                documento=documento,
                versao_embedding=utils.VERSAO_EMBEDDING,
            )
        )

    await db.commit()
    logger.info("%s: %d chunk(s) ingerido(s).", nome, len(itens))
    return True


async def ingest(forcar: bool = False) -> int:
    """Ingere todos os PDFs de ``PASTA_PDF``.

    Retorna a quantidade de arquivos que falharam; um PDF com problema não
    interrompe os demais, mas o erro é registrado no log.
    """
    if not os.path.isdir(PASTA_PDF):
        raise FileNotFoundError(
            f"diretório {PASTA_PDF!r} não encontrado; coloque os PDFs nele."
        )

    arquivos = sorted(
        arquivo for arquivo in os.listdir(PASTA_PDF) if arquivo.lower().endswith(".pdf")
    )
    if not arquivos:
        logger.warning("nenhum PDF encontrado em %s.", PASTA_PDF)
        return 0

    falhas = 0
    try:
        async with AsyncSession(engine) as db:
            for arquivo in arquivos:
                try:
                    await ingerir_arquivo(
                        db, os.path.join(PASTA_PDF, arquivo), forcar=forcar
                    )
                except Exception:
                    await db.rollback()
                    falhas += 1
                    logger.exception("falha ao ingerir %s.", arquivo)
    finally:
        await engine.dispose()

    return falhas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="re-ingere PDFs já presentes no banco"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    falhas = asyncio.run(ingest(forcar=args.force))
    if falhas:
        logger.error("%d arquivo(s) falharam.", falhas)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
