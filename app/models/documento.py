import sqlalchemy as sa
import sqlalchemy.orm as so

from app import Base


class Documento(Base):
    __tablename__ = "documento"

    id: so.Mapped[int] = so.mapped_column(sa.Integer(), primary_key=True)
    nome: so.Mapped[str] = so.mapped_column(sa.String(255))
    # SHA-256 do PDF: evita ingerir o mesmo arquivo duas vezes.
    hash: so.Mapped[str | None] = so.mapped_column(
        sa.String(64), unique=True, index=True, nullable=True
    )
    chunks: so.Mapped[list["Chunk"]] = so.relationship(back_populates="documento")
