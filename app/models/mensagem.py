from datetime import datetime
from enum import Enum

import sqlalchemy as sa
import sqlalchemy.orm as so

from app import Base


class Role(Enum):
    USER = 'user'
    ASSISTANT = 'assistant'


class Mensagem(Base):
    __tablename__ = 'mensagem'

    id: so.Mapped[int] = so.mapped_column(sa.Integer(), primary_key=True)
    conteudo: so.Mapped[str] = so.mapped_column(sa.Text())
    role: so.Mapped[Role] = so.mapped_column(sa.Enum(Role))
    sessao: so.Mapped['Sessao'] = so.relationship(back_populates='mensagens')
    sessao_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('sessao.id'))
    criado_em: so.Mapped[datetime] = so.mapped_column(sa.DateTime(), default=datetime.now)
    atualizado_em: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(),
        default=datetime.now,
        onupdate=datetime.now
    )
