from pydantic import BaseModel


class ChatPostSchema(BaseModel):
    conteudo: str
