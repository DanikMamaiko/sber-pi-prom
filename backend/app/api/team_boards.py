import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.db.session import get_session
from app.schemas.pi_cycle import (
    CapacityRead,
    CapacityWrite,
    TeamBoardsRead,
    TeamBoardsWrite,
)
from app.services.capacity import read_capacity, replace_capacity
from app.services.optimistic_locking import lock_cycle
from app.services.team_boards import read_team_boards, replace_team_boards

router = APIRouter(tags=["PI Cycle"])


@router.get("/pi-cycles/{cycle_id}/team-boards", response_model=TeamBoardsRead)
async def get_team_boards(
    cycle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    cycle = await get_cycle_or_404(session, cycle_id)
    return await read_team_boards(session, cycle)


@router.put("/pi-cycles/{cycle_id}/team-boards", response_model=TeamBoardsRead)
async def put_team_boards(
    cycle_id: uuid.UUID,
    payload: TeamBoardsWrite,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await replace_team_boards(session, cycle, payload)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("/pi-cycles/{cycle_id}/capacity", response_model=CapacityRead)
async def get_capacity(
    cycle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    cycle = await get_cycle_or_404(session, cycle_id)
    return await read_capacity(session, cycle)


@router.put("/pi-cycles/{cycle_id}/capacity", response_model=CapacityRead)
async def put_capacity(
    cycle_id: uuid.UUID,
    payload: CapacityWrite,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await replace_capacity(session, cycle, payload)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


