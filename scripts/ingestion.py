import asyncio
import itertools
import os
from time import sleep

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


def normalizar_nome(nome: str) -> str:
    return nome.replace("-", " ").title()


async def ingest():
    db = AsyncSession(engine)

    for file in os.listdir("data/raw/"):
        documento = Documento(nome=normalizar_nome(file))
        db.add(documento)

        chunks = []
        with pymupdf.open(f"data/raw/{file}") as doc:
            for page in doc:
                chunks += chunk_page(page.get_text())

        embeddings = model.encode(
            chunks,
            normalize_embeddings=True,
        )
        for chunk, embedding in zip(chunks, embeddings):
            db.add(
                Chunk(
                    conteudo=chunk,
                    embedding=embedding,
                    pagina=0,
                    documento=documento,
                )
            )

        await db.commit()
        await db.close()


if __name__ == "__main__":
    asyncio.run(ingest())
