from pydantic import BaseModel


class SessaoUpdateSchema(BaseModel):
    titulo: str
