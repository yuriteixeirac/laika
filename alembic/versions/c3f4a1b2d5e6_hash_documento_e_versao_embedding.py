"""hash do documento e versão do embedding

Revision ID: c3f4a1b2d5e6
Revises: fd84ae0b6dbf
Create Date: 2026-09-21 19:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f4a1b2d5e6"
down_revision: Union[str, Sequence[str], None] = "fd84ae0b6dbf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Idempotência da ingestão: hash do PDF, único quando preenchido.
    op.add_column("documento", sa.Column("hash", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_documento_hash"), "documento", ["hash"], unique=True)

    # Versionamento do embedding: chunks de modelos antigos deixam de ser usados.
    op.add_column(
        "chunk", sa.Column("versao_embedding", sa.String(length=128), nullable=True)
    )
    op.create_index(
        op.f("ix_chunk_versao_embedding"), "chunk", ["versao_embedding"], unique=False
    )

    # A revisão fd84ae0b6dbf removeu o índice HNSW por engano; a busca vetorial
    # (ORDER BY embedding <=> :consulta) depende dele.
    op.execute(
        "CREATE INDEX IF NOT EXISTS chunk_embedding_idx ON chunk "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS chunk_embedding_idx")
    op.drop_index(op.f("ix_chunk_versao_embedding"), table_name="chunk")
    op.drop_column("chunk", "versao_embedding")
    op.drop_index(op.f("ix_documento_hash"), table_name="documento")
    op.drop_column("documento", "hash")
