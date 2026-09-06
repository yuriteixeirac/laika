import os

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

load_dotenv()

app = FastAPI()
engine = create_engine(url=os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///sqlite3.db'))
oauth = OAuth()

oauth.register(
    'suap',
    client_id=os.getenv('SUAP_CLIENT_ID'),
    client_secret=os.getenv('SUAP_CLIENT_ID'),
    authorize_url='https://suap.ifrn.edu.br/o/authorize/',
    access_token_url="https://suap.ifrn.edu.br/o/token/",
    api_base_url="https://suap.ifrn.edu.br/api/",
)


Base = declarative_base()

from app.auth import auth_router

app.include_router(auth_router)

@app.get('/health')
async def home():
    return {
        'msg': 'API funcionando e pronta para uso!'
    }
