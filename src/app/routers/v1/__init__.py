from fastapi import APIRouter

from app.routers.v1 import generate

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(generate.router)
