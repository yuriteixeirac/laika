import sqlalchemy as sa
import sqlalchemy.orm as so

from app import Base


class Documento(Base):
    __tablename__ = "documento"

    id: so.Mapped[int] = so.mapped_column(sa.Integer(), primary_key=True)
    nome: so.Mapped[str] = so.mapped_column(sa.String(255))
    chunks: so.Mapped[list["Chunk"]] = so.relationship(back_populates="documento")
