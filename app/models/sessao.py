from datetime import datetime

import sqlalchemy as sa
import sqlalchemy.orm as so

from app import Base


class Sessao(Base):
    __tablename__ = 'sessao'

    id: so.Mapped[int] = so.mapped_column(sa.Integer(), primary_key=True)
    titulo: so.Mapped[str] = so.mapped_column(sa.String(255))
    usuario: so.Mapped['Usuario'] = so.relationship(back_populates='sessoes')
    usuario_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('usuario.id'))
    criado_em: so.Mapped[datetime] = so.mapped_column(sa.DateTime(), default=datetime.now)
    atualizado_em: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(),
        default=datetime.now,
        onupdate=datetime.now
    )
