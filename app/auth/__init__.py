from fastapi import APIRouter

auth_router = APIRouter(
    prefix='/auth'
)

from . import models
