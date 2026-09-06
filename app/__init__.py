import os

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

load_dotenv()

app = FastAPI()
engine = create_engine(
    url=os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///sqlite3.db')
)
Base = declarative_base()

from app.auth import auth_router

app.include_router(auth_router)

@app.get('/health')
async def home():
    return {
        'msg': 'API funcionando e pronta para uso!'
    }
