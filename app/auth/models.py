from datetime import datetime

import sqlalchemy as sa
import sqlalchemy.orm as so

from app import Base


class Usuario(Base):
    __tablename__ = 'usuario'

    id: so.Mapped[int] = so.mapped_column(sa.Integer(), primary_key=True)
    nome: so.Mapped[str] = so.mapped_column(sa.String(255))
    matricula: so.Mapped[str] = so.mapped_column(sa.String(14), index=True, unique=True)
    email: so.Mapped[str] = so.mapped_column(sa.String(255), unique=True)
    criado_em: so.Mapped[datetime] = so.mapped_column(sa.DateTime(), default=datetime.now)
    atualizado_em: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(),
        default=datetime.now,
        onupdate=datetime.now
    )
