import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.auth.dependencies import require_http_permission
from app.auth.permissions import Permission
from app.db.session import get_session
from app.models.pi_cycle import Initiative, InitiativeExecutor
from app.schemas.pi_cycle import (
    InitiativeCreate,
    InitiativeRead,
    PrePiDeleteCommand,
    PrePiInitiativeCommand,
    PrePiMoveCommand,
    PrePiRead,
    PrePiSubmitRead,
    PrePiSubmitWrite,
    PrePiWrite,
)
from app.services.goals import PrePiValidationError, submit_pre_pi
from app.services.optimistic_locking import lock_cycle
from app.services.pre_pi import (
    PrePiCascadeRequired,
    delete_pre_pi_initiative,
    move_pre_pi_initiative,
    read_pre_pi,
    replace_pre_pi,
    update_pre_pi_initiative,
)
from app.services.validation import cycle_team_context, normalized_effort

router = APIRouter(
    tags=["PI Cycle"],
    dependencies=[Depends(require_http_permission(Permission.PRE_PI_READ, Permission.PRE_PI_WRITE))],
)


@router.get("/pi-cycles/{cycle_id}/pre-pi", response_model=PrePiRead)
async def get_pre_pi(
    cycle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    cycle = await get_cycle_or_404(session, cycle_id)
    return await read_pre_pi(session, cycle)


@router.put("/pi-cycles/{cycle_id}/pre-pi", response_model=PrePiRead)
async def put_pre_pi(
    cycle_id: uuid.UUID,
    payload: PrePiWrite,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await replace_pre_pi(session, cycle, payload)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error))


@router.patch(
    "/pi-cycles/{cycle_id}/pre-pi/initiatives/{initiative_id}",
    response_model=PrePiRead,
)
async def patch_pre_pi_initiative(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    payload: PrePiInitiativeCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await update_pre_pi_initiative(session, cycle, initiative_id, payload)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error))


@router.post(
    "/pi-cycles/{cycle_id}/pre-pi/initiatives/{initiative_id}/move",
    response_model=PrePiRead,
)
async def post_pre_pi_move(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    payload: PrePiMoveCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await move_pre_pi_initiative(session, cycle, initiative_id, payload)
    except PrePiCascadeRequired as error:
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


@router.delete(
    "/pi-cycles/{cycle_id}/pre-pi/initiatives/{initiative_id}",
    response_model=PrePiRead,
)
async def remove_pre_pi_initiative(
    cycle_id: uuid.UUID,
    initiative_id: uuid.UUID,
    payload: PrePiDeleteCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await delete_pre_pi_initiative(session, cycle, initiative_id, payload)
    except PrePiCascadeRequired as error:
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


@router.post("/pi-cycles/{cycle_id}/pre-pi/submit", response_model=PrePiSubmitRead)
async def post_pre_pi_submit(
    cycle_id: uuid.UUID,
    payload: PrePiSubmitWrite,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await submit_pre_pi(session, cycle, payload)
    except PrePiValidationError as error:
        await session.rollback()
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Заполните обязательные поля Pre PI",
                "problems": error.problems,
            },
        )
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error))


@router.post(
    "/pi-cycles/{cycle_id}/initiatives",
    response_model=InitiativeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_initiative(
    cycle_id: uuid.UUID,
    payload: InitiativeCreate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id)
    if await session.scalar(
        select(Initiative).where(
            Initiative.cycle_id == cycle_id,
            func.lower(Initiative.issue_key) == payload.issue_key.strip().lower(),
        )
    ):
        raise HTTPException(
            status_code=422,
            detail="Issue должен быть уникален в пределах PI-цикла",
        )
    _, _, competencies_by_team = await cycle_team_context(session, cycle.id)
    team_ids = [row.team_id for row in payload.executors]
    if len(team_ids) > 1:
        raise HTTPException(
            status_code=422,
            detail="В компетенциях команды владельца может быть только одна команда",
        )
    if payload.owner_team_id is not None and payload.owner_team_id not in competencies_by_team:
        raise HTTPException(
            status_code=422,
            detail="Команда-владелец не входит в данный PI-цикл",
        )
    normalized_executors = []
    try:
        for executor in payload.executors:
            if executor.team_id not in competencies_by_team:
                raise ValueError(f"Команда-исполнитель не входит в данный PI-цикл: {executor.team_id}")
            if payload.owner_team_id is None or executor.team_id != payload.owner_team_id:
                raise ValueError("В компетенциях можно указывать только ресурсы команды-владельца")
            normalized_executors.append(
                (
                    executor.team_id,
                    normalized_effort(
                        executor.effort_by_competency,
                        competencies_by_team[executor.team_id],
                        f"Инициатива {payload.issue_key}",
                    ),
                )
            )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    data = payload.model_dump(exclude={"executors"})
    data["issue_key"] = payload.issue_key.strip()
    initiative = Initiative(cycle_id=cycle_id, **data)
    initiative.executors = [
        InitiativeExecutor(team_id=team_id, effort_by_competency=effort)
        for team_id, effort in normalized_executors
    ]
    session.add(initiative)
    await session.commit()
    await session.refresh(initiative)
    return initiative


@router.get("/pi-cycles/{cycle_id}/initiatives", response_model=list[InitiativeRead])
async def list_initiatives(cycle_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    await get_cycle_or_404(session, cycle_id)
    result = await session.scalars(
        select(Initiative)
        .where(Initiative.cycle_id == cycle_id)
        .order_by(Initiative.sort_order, Initiative.created_at)
    )
    return result.all()


