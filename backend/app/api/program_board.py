import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.db.session import get_session
from app.schemas.pi_cycle import ProgramBoardRead, ProgramBoardWrite
from app.services.optimistic_locking import lock_cycle
from app.services.program_board import read_program_board, replace_program_board

router = APIRouter(tags=["PI Cycle"])


@router.get("/pi-cycles/{cycle_id}/program-board", response_model=ProgramBoardRead)
async def get_program_board(
    cycle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    cycle = await get_cycle_or_404(session, cycle_id)
    return await read_program_board(session, cycle)


@router.put("/pi-cycles/{cycle_id}/program-board", response_model=ProgramBoardRead)
async def put_program_board(
    cycle_id: uuid.UUID,
    payload: ProgramBoardWrite,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await replace_program_board(session, cycle, payload)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


