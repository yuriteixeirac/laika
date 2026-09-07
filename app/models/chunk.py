import sqlalchemy as sa
import sqlalchemy.orm as so
from pgvector.sqlalchemy import Vector

from app import Base


class Chunk(Base):
    __tablename__ = 'chunk'

    id: so.Mapped[int] = so.mapped_column(sa.Integer(), primary_key=True)
    conteudo: so.Mapped[str] = so.mapped_column(sa.Text())
    embedding: so.Mapped[list[float]] = so.mapped_column(Vector(384))
    documento: so.Mapped['Documento'] = so.relationship(back_populates='chunks')
    documento_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('documento.id'))
