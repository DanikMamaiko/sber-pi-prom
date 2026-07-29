import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.db.session import get_session
from app.schemas.pi_cycle import (
    CapacityRead,
    CapacityMemberCreate,
    CapacityMemberUpdate,
    CapacityWrite,
    TeamBoardDeleteCommand,
    TeamBoardInitiativeCommand,
    TeamBoardStoryCreate,
    TeamBoardStoryUpdate,
    TeamBoardWorkItemCreate,
    TeamBoardWorkItemUpdate,
    TeamBoardsRead,
    TeamBoardsWrite,
)
from app.services.capacity import (
    create_capacity_member,
    delete_capacity_member,
    read_capacity,
    replace_capacity,
    update_capacity_member,
)
from app.services.optimistic_locking import lock_cycle
from app.services.team_boards import (
    TeamBoardCascadeRequired,
    create_board_story,
    create_board_work_item,
    delete_board_story,
    delete_board_work_item,
    read_team_boards,
    replace_team_boards,
    update_board_initiative,
    update_board_story,
    update_board_work_item,
)

router = APIRouter(tags=["PI Cycle"])


async def _run_board_command(session: AsyncSession, operation):
    try:
        return await operation
    except TeamBoardCascadeRequired as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "cascade_confirmation_required",
                "message": error.message,
                "affected": error.affected,
            },
        )
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


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


@router.patch(
    "/pi-cycles/{cycle_id}/team-boards/initiatives/{initiative_id}",
    response_model=TeamBoardsRead,
)
async def patch_team_board_initiative(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    payload: TeamBoardInitiativeCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_board_command(
        session, update_board_initiative(session, cycle, initiative_id, payload)
    )


@router.post(
    "/pi-cycles/{cycle_id}/team-boards/initiatives/{initiative_id}/stories",
    response_model=TeamBoardsRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_team_board_story(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    payload: TeamBoardStoryCreate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_board_command(
        session, create_board_story(session, cycle, initiative_id, payload)
    )


@router.patch(
    "/pi-cycles/{cycle_id}/team-boards/initiatives/{initiative_id}/stories/{story_id}",
    response_model=TeamBoardsRead,
)
async def patch_team_board_story(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    story_id: uuid.UUID,
    payload: TeamBoardStoryUpdate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_board_command(
        session, update_board_story(session, cycle, initiative_id, story_id, payload)
    )


@router.delete(
    "/pi-cycles/{cycle_id}/team-boards/initiatives/{initiative_id}/stories/{story_id}",
    response_model=TeamBoardsRead,
)
async def remove_team_board_story(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    story_id: uuid.UUID,
    payload: TeamBoardDeleteCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_board_command(
        session, delete_board_story(session, cycle, initiative_id, story_id, payload)
    )


@router.post(
    "/pi-cycles/{cycle_id}/team-boards/initiatives/{initiative_id}/work-items",
    response_model=TeamBoardsRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_team_board_work_item(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    payload: TeamBoardWorkItemCreate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_board_command(
        session, create_board_work_item(session, cycle, initiative_id, payload)
    )


@router.patch(
    "/pi-cycles/{cycle_id}/team-boards/initiatives/{initiative_id}/work-items/{work_item_id}",
    response_model=TeamBoardsRead,
)
async def patch_team_board_work_item(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    work_item_id: uuid.UUID,
    payload: TeamBoardWorkItemUpdate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_board_command(
        session,
        update_board_work_item(session, cycle, initiative_id, work_item_id, payload),
    )


@router.delete(
    "/pi-cycles/{cycle_id}/team-boards/initiatives/{initiative_id}/work-items/{work_item_id}",
    response_model=TeamBoardsRead,
)
async def remove_team_board_work_item(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    work_item_id: uuid.UUID,
    payload: TeamBoardDeleteCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_board_command(
        session,
        delete_board_work_item(session, cycle, initiative_id, work_item_id, payload),
    )


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


@router.post(
    "/pi-cycles/{cycle_id}/capacity/members",
    response_model=CapacityRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_capacity_member(
    cycle_id: uuid.UUID,
    payload: CapacityMemberCreate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_board_command(session, create_capacity_member(session, cycle, payload))


@router.patch(
    "/pi-cycles/{cycle_id}/capacity/members/{member_id}",
    response_model=CapacityRead,
)
async def patch_capacity_member(
    cycle_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: CapacityMemberUpdate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_board_command(
        session, update_capacity_member(session, cycle, member_id, payload)
    )


@router.delete(
    "/pi-cycles/{cycle_id}/capacity/members/{member_id}",
    response_model=CapacityRead,
)
async def remove_capacity_member(
    cycle_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: TeamBoardDeleteCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_board_command(
        session,
        delete_capacity_member(
            session, cycle, member_id, confirm_cascade=payload.confirm_cascade
        ),
    )


