import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.db.session import get_session
from app.models.pi_cycle import Initiative, PiCycleTeam, PiGoal
from app.schemas.pi_cycle import (
    GoalCreateCommand,
    GoalDeleteCommand,
    GoalLinkCommand,
    GoalReorderCommand,
    GoalStatusCommand,
    GoalUnlinkCommand,
    GoalUpdateCommand,
    GoalsRead,
    GoalsWrite,
    PiGoalCreate,
    PiGoalRead,
)
from app.services.goals import (
    GoalsCascadeRequired,
    add_goal_link_command,
    create_goal_command,
    delete_goal_command,
    read_goals,
    remove_goal_link_command,
    reorder_goals_command,
    replace_goals,
    update_goal_command,
    update_goal_status_command,
)
from app.services.optimistic_locking import lock_cycle

router = APIRouter(tags=["PI Cycle"])


async def _run_goal_command(session: AsyncSession, operation):
    try:
        return await operation
    except GoalsCascadeRequired as error:
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
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/pi-cycles/{cycle_id}/goals-board", response_model=GoalsRead)
async def get_goals_board(
    cycle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    cycle = await get_cycle_or_404(session, cycle_id)
    return await read_goals(session, cycle)


@router.put("/pi-cycles/{cycle_id}/goals-board", response_model=GoalsRead)
async def put_goals_board(
    cycle_id: uuid.UUID,
    payload: GoalsWrite,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await replace_goals(session, cycle, payload)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error))


@router.post(
    "/pi-cycles/{cycle_id}/goals-board/goals",
    response_model=GoalsRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_goals_board_goal(
    cycle_id: uuid.UUID,
    payload: GoalCreateCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_goal_command(session, create_goal_command(session, cycle, payload))


@router.patch("/pi-cycles/{cycle_id}/goals-board/goals/{goal_id}", response_model=GoalsRead)
async def patch_goals_board_goal(
    cycle_id: uuid.UUID,
    goal_id: uuid.UUID,
    payload: GoalUpdateCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_goal_command(session, update_goal_command(session, cycle, goal_id, payload))


@router.delete("/pi-cycles/{cycle_id}/goals-board/goals/{goal_id}", response_model=GoalsRead)
async def delete_goals_board_goal(
    cycle_id: uuid.UUID,
    goal_id: uuid.UUID,
    payload: GoalDeleteCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_goal_command(session, delete_goal_command(session, cycle, goal_id, payload))


@router.put("/pi-cycles/{cycle_id}/goals-board/order", response_model=GoalsRead)
async def put_goals_board_order(
    cycle_id: uuid.UUID,
    payload: GoalReorderCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_goal_command(session, reorder_goals_command(session, cycle, payload))


@router.patch(
    "/pi-cycles/{cycle_id}/goals-board/goals/{goal_id}/status",
    response_model=GoalsRead,
)
async def patch_goals_board_goal_status(
    cycle_id: uuid.UUID,
    goal_id: uuid.UUID,
    payload: GoalStatusCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_goal_command(
        session,
        update_goal_status_command(session, cycle, goal_id, payload),
    )


@router.post(
    "/pi-cycles/{cycle_id}/goals-board/goals/{goal_id}/links",
    response_model=GoalsRead,
)
async def post_goals_board_goal_link(
    cycle_id: uuid.UUID,
    goal_id: uuid.UUID,
    payload: GoalLinkCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_goal_command(session, add_goal_link_command(session, cycle, goal_id, payload))


@router.delete(
    "/pi-cycles/{cycle_id}/goals-board/goals/{goal_id}/links/{initiative_id}",
    response_model=GoalsRead,
)
async def delete_goals_board_goal_link(
    cycle_id: uuid.UUID,
    goal_id: uuid.UUID,
    initiative_id: uuid.UUID,
    payload: GoalUnlinkCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_goal_command(
        session,
        remove_goal_link_command(session, cycle, goal_id, initiative_id, payload),
    )


@router.get("/pi-cycles/{cycle_id}/goals", response_model=list[PiGoalRead])
async def list_goals(cycle_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    await get_cycle_or_404(session, cycle_id)
    result = await session.scalars(
        select(PiGoal).where(PiGoal.cycle_id == cycle_id).order_by(PiGoal.sort_order)
    )
    return result.all()


@router.post("/pi-cycles/{cycle_id}/goals", response_model=PiGoalRead, status_code=status.HTTP_201_CREATED)
async def create_goal(
    cycle_id: uuid.UUID,
    payload: PiGoalCreate,
    session: AsyncSession = Depends(get_session),
):
    await lock_cycle(session, cycle_id)
    if payload.team_id is not None and not await session.scalar(
        select(PiCycleTeam).where(
            PiCycleTeam.cycle_id == cycle_id,
            PiCycleTeam.team_id == payload.team_id,
        )
    ):
        raise HTTPException(
            status_code=422,
            detail="Команда цели не входит в данный PI-цикл",
        )
    if payload.initiative_id is not None and not await session.scalar(
        select(Initiative).where(
            Initiative.cycle_id == cycle_id,
            Initiative.id == payload.initiative_id,
        )
    ):
        raise HTTPException(
            status_code=422,
            detail="Инициатива цели не входит в данный PI-цикл",
        )
    goal = PiGoal(cycle_id=cycle_id, **payload.model_dump())
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return goal


