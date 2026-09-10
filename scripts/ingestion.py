import asyncio
import os

import pymupdf
from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine
from app.models import Chunk, Documento

model = SentenceTransformer("intfloat/multilingual-e5-base")


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


def get_chunks(chunkset: list[tuple[int, list[str]]]) -> list[str]:
    """Transforma a estrutura de tuple[int, list[str]] em uma única lista contendo todos os chunks."""
    total = []
    for c in chunkset:
        total += c[1]
    return total


def normalizar_nome(nome: str) -> str:
    return nome.replace(".pdf", "").replace("-", " ").title()


async def ingest():
    db = AsyncSession(engine)

    for file in os.listdir("data/raw/"):
        documento = Documento(nome=normalizar_nome(file))
        db.add(documento)

        chunks = []
        with pymupdf.open(f"data/raw/{file}") as doc:
            for page in doc:
                chunks.append(
                    (page.number, chunk_page(page.get_text())),
                )

        embeddings = model.encode(
            get_chunks(chunks),
            normalize_embeddings=True,
        )
        for page, chunkset in chunks:
            counter = 0
            for chunk, embedding in zip(chunkset, embeddings):
                db.add(
                    Chunk(
                        conteudo=chunk,
                        embedding=embedding,
                        pagina=page,
                        documento=documento,
                    )
                )
                counter += 1
            embeddings = embeddings[counter:]

        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
        await db.close()


if __name__ == "__main__":
    asyncio.run(ingest())
