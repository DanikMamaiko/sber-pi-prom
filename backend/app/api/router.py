from fastapi import APIRouter

from app.api import pi_cycles

api_router = APIRouter(prefix="/api")
api_router.include_router(pi_cycles.router)

