from fastapi import APIRouter

from app.api import (
    _common,
    auth,
    backlog,
    goals,
    navigation,
    pi_cycle_data,
    pre_pi,
    program_board,
    risks,
    team_boards,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(_common.router)
api_router.include_router(auth.router)
api_router.include_router(navigation.router)
api_router.include_router(pi_cycle_data.router)
api_router.include_router(backlog.router)
api_router.include_router(pre_pi.router)
api_router.include_router(goals.router)
api_router.include_router(team_boards.router)
api_router.include_router(program_board.router)
api_router.include_router(risks.router)
