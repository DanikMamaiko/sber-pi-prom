import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.auth.dependencies import require_http_permission
from app.auth.permissions import Permission
from app.db.session import get_session
from app.schemas.pi_cycle import (
    ProgramBoardCommand,
    ProgramBoardConnectionCreate,
    ProgramBoardConnectionUpdate,
    ProgramBoardMoveCommand,
    ProgramBoardRead,
    ProgramBoardWrite,
)
from app.services.optimistic_locking import lock_cycle
from app.services.program_board import (
    create_program_board_connection,
    delete_program_board_connection,
    move_program_board_initiative,
    read_program_board,
    replace_program_board,
    update_program_board_connection,
)

router = APIRouter(
    tags=["PI Cycle"],
    dependencies=[
        Depends(
            require_http_permission(Permission.PROGRAM_BOARD_READ, Permission.PROGRAM_BOARD_WRITE)
        )
    ],
)


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
        raise HTTPException(status_code=422, detail=str(error))


async def _run_command(session: AsyncSession, operation):
    try:
        return await operation
    except ValueError as error:
        await session.rollback()
        raise HTTPException(
            status_code=422, detail=str(error)
        )


@router.patch(
    "/pi-cycles/{cycle_id}/program-board/initiatives/{initiative_id}/position",
    response_model=ProgramBoardRead,
)
async def patch_program_board_position(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    payload: ProgramBoardMoveCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_command(
        session,
        move_program_board_initiative(session, cycle, initiative_id, payload),
    )


@router.post(
    "/pi-cycles/{cycle_id}/program-board/connections",
    response_model=ProgramBoardRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_program_board_connection(
    cycle_id: uuid.UUID,
    payload: ProgramBoardConnectionCreate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_command(
        session, create_program_board_connection(session, cycle, payload)
    )


@router.patch(
    "/pi-cycles/{cycle_id}/program-board/connections/{connection_id}",
    response_model=ProgramBoardRead,
)
async def patch_program_board_connection(
    cycle_id: uuid.UUID,
    connection_id: uuid.UUID,
    payload: ProgramBoardConnectionUpdate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_command(
        session,
        update_program_board_connection(
            session, cycle, connection_id, payload
        ),
    )


@router.delete(
    "/pi-cycles/{cycle_id}/program-board/connections/{connection_id}",
    response_model=ProgramBoardRead,
)
async def remove_program_board_connection(
    cycle_id: uuid.UUID,
    connection_id: uuid.UUID,
    payload: ProgramBoardCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_command(
        session, delete_program_board_connection(session, cycle, connection_id)
    )


