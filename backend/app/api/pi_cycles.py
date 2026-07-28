import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.pi_cycle import (
    BacklogItem,
    Initiative,
    InitiativeExecutor,
    PiCycle,
    PiCycleTeam,
    PiGoal,
    Risk,
    Team,
    TeamCompetency,
    TeamMember,
    Tribe,
)
from app.schemas.pi_cycle import (
    BacklogBoardRead,
    BacklogBoardWrite,
    BacklogDispatchWrite,
    BacklogItemCommand,
    BacklogItemDelete,
    BacklogReorderCommand,
    CapacityRead,
    CapacityWrite,
    GoalsRead,
    GoalsWrite,
    InitiativeCreate,
    InitiativeRead,
    OverviewRead,
    PiCycleCreate,
    PiCycleDataCommand,
    PiCycleDataRead,
    PiCycleDataReplace,
    PiCycleDataUpdate,
    PiCycleRead,
    PiCycleTeamDataCreate,
    PiCycleTeamDataUpdate,
    PiCycleTeamDelete,
    PiEventDataCreate,
    PiEventDataUpdate,
    PiGoalOptionDataCreate,
    PiGoalOptionDataUpdate,
    PiCycleSetupRead,
    PiCycleSetupWrite,
    PiTagDataCreate,
    PiTagDataUpdate,
    PiCycleUpdate,
    PrePiRead,
    PrePiDeleteCommand,
    PrePiInitiativeCommand,
    PrePiMoveCommand,
    PrePiSubmitRead,
    PrePiSubmitWrite,
    PrePiWrite,
    ProgramBoardRead,
    ProgramBoardWrite,
    PiGoalCreate,
    PiGoalRead,
    RiskCreate,
    RiskRead,
    RisksRead,
    RisksWrite,
    TeamCreate,
    TeamBoardsRead,
    TeamBoardsWrite,
    TeamMemberCreate,
    TeamMemberRead,
    TeamRead,
    TribeCreate,
    TribeRead,
)
from app.services.planning import compute_sprints
from app.services.cycle_setup import read_cycle_setup, replace_cycle_setup
from app.services.backlog_board import (
    BacklogCascadeRequired,
    BacklogNotFound,
    create_backlog_item,
    delete_backlog_item,
    dispatch_backlog_items,
    read_backlog_board,
    reorder_backlog_items,
    replace_backlog_board,
    update_backlog_item,
)
from app.services.pre_pi import (
    PrePiCascadeRequired,
    delete_pre_pi_initiative,
    move_pre_pi_initiative,
    read_pre_pi,
    replace_pre_pi,
    update_pre_pi_initiative,
)
from app.services.goals import (
    PrePiValidationError,
    read_goals,
    replace_goals,
    submit_pre_pi,
)
from app.services.team_boards import read_team_boards, replace_team_boards
from app.services.capacity import read_capacity, replace_capacity
from app.services.program_board import read_program_board, replace_program_board
from app.services.risks import read_risks, replace_risks
from app.services.validation import cycle_team_context, normalized_effort
from app.services.optimistic_locking import lock_backlog, lock_cycle
from app.services.pi_cycle_data import (
    CascadeRequired,
    create_cycle_team,
    create_goal_option,
    create_pir,
    create_tag,
    delete_cycle_team,
    delete_goal_option,
    delete_pir,
    delete_tag,
    read_pi_cycle_data,
    replace_pi_cycle_data,
    update_cycle_data,
    update_cycle_team,
    update_goal_option,
    update_pir,
    update_tag,
)


router = APIRouter(tags=["PI Cycle"])


async def get_cycle_or_404(session: AsyncSession, cycle_id: uuid.UUID) -> PiCycle:
    cycle = await session.get(PiCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PI cycle not found")
    return cycle


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/pi-cycles", response_model=list[PiCycleRead])
async def list_pi_cycles(session: AsyncSession = Depends(get_session)):
    result = await session.scalars(select(PiCycle).order_by(PiCycle.year, PiCycle.quarter))
    return result.all()


@router.post("/pi-cycles", response_model=PiCycleRead, status_code=status.HTTP_201_CREATED)
async def create_pi_cycle(payload: PiCycleCreate, session: AsyncSession = Depends(get_session)):
    existing = await session.scalar(
        select(PiCycle).where(PiCycle.year == payload.year, PiCycle.quarter == payload.quarter)
    )
    if existing:
        return existing
    cycle = PiCycle(**payload.model_dump())
    cycle.setup_initialized = True
    session.add(cycle)
    await session.commit()
    await session.refresh(cycle)
    return cycle


@router.post(
    "/pi-cycle-data",
    response_model=PiCycleDataRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_pi_cycle_data(
    payload: PiCycleCreate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await session.scalar(
        select(PiCycle).where(PiCycle.year == payload.year, PiCycle.quarter == payload.quarter)
    )
    if cycle is None:
        cycle = PiCycle(**payload.model_dump(), setup_initialized=True)
        session.add(cycle)
        await session.commit()
        await session.refresh(cycle)
    return await read_pi_cycle_data(session, cycle)


async def _run_pi_data_command(session: AsyncSession, operation):
    try:
        return await operation
    except CascadeRequired as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.detail)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.patch("/pi-cycles/{cycle_id}", response_model=PiCycleRead)
async def update_pi_cycle(
    cycle_id: uuid.UUID,
    payload: PiCycleUpdate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    for key, value in payload.model_dump(
        exclude_unset=True, exclude={"expected_version"}
    ).items():
        setattr(cycle, key, value)
    await session.commit()
    await session.refresh(cycle)
    return cycle


@router.get("/pi-cycles/{cycle_id}/setup", response_model=PiCycleSetupRead)
async def get_pi_cycle_setup(
    cycle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    cycle = await get_cycle_or_404(session, cycle_id)
    return await read_cycle_setup(session, cycle)


@router.put("/pi-cycles/{cycle_id}/setup", response_model=PiCycleSetupRead)
async def put_pi_cycle_setup(
    cycle_id: uuid.UUID,
    payload: PiCycleSetupWrite,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await replace_cycle_setup(session, cycle, payload)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("/pi-cycles/{cycle_id}/data", response_model=PiCycleDataRead)
async def get_pi_cycle_data(
    cycle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    cycle = await get_cycle_or_404(session, cycle_id)
    return await read_pi_cycle_data(session, cycle)


@router.patch("/pi-cycles/{cycle_id}/data", response_model=PiCycleDataRead)
async def patch_pi_cycle_data(
    cycle_id: uuid.UUID,
    payload: PiCycleDataUpdate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, update_cycle_data(session, cycle, payload))


@router.put("/pi-cycles/{cycle_id}/data", response_model=PiCycleDataRead)
async def put_pi_cycle_data(
    cycle_id: uuid.UUID,
    payload: PiCycleDataReplace,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, replace_pi_cycle_data(session, cycle, payload))


@router.post("/pi-cycles/{cycle_id}/pirs", response_model=PiCycleDataRead)
async def post_pi_cycle_pir(
    cycle_id: uuid.UUID,
    payload: PiEventDataCreate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, create_pir(session, cycle, payload))


@router.patch("/pi-cycles/{cycle_id}/pirs/{pir_id}", response_model=PiCycleDataRead)
async def patch_pi_cycle_pir(
    cycle_id: uuid.UUID,
    pir_id: uuid.UUID,
    payload: PiEventDataUpdate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, update_pir(session, cycle, pir_id, payload))


@router.delete("/pi-cycles/{cycle_id}/pirs/{pir_id}", response_model=PiCycleDataRead)
async def remove_pi_cycle_pir(
    cycle_id: uuid.UUID,
    pir_id: uuid.UUID,
    payload: PiCycleDataCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, delete_pir(session, cycle, pir_id))


@router.post("/pi-cycles/{cycle_id}/cycle-teams", response_model=PiCycleDataRead)
async def post_pi_cycle_team(
    cycle_id: uuid.UUID,
    payload: PiCycleTeamDataCreate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, create_cycle_team(session, cycle, payload))


@router.patch(
    "/pi-cycles/{cycle_id}/cycle-teams/{cycle_team_id}",
    response_model=PiCycleDataRead,
)
async def patch_pi_cycle_team(
    cycle_id: uuid.UUID,
    cycle_team_id: uuid.UUID,
    payload: PiCycleTeamDataUpdate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(
        session,
        update_cycle_team(session, cycle, cycle_team_id, payload),
    )


@router.delete(
    "/pi-cycles/{cycle_id}/cycle-teams/{cycle_team_id}",
    response_model=PiCycleDataRead,
)
async def remove_pi_cycle_team(
    cycle_id: uuid.UUID,
    cycle_team_id: uuid.UUID,
    payload: PiCycleTeamDelete,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(
        session,
        delete_cycle_team(session, cycle, cycle_team_id, payload),
    )


@router.post("/pi-cycles/{cycle_id}/goal-options", response_model=PiCycleDataRead)
async def post_pi_cycle_goal_option(
    cycle_id: uuid.UUID,
    payload: PiGoalOptionDataCreate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, create_goal_option(session, cycle, payload))


@router.patch(
    "/pi-cycles/{cycle_id}/goal-options/{option_id}",
    response_model=PiCycleDataRead,
)
async def patch_pi_cycle_goal_option(
    cycle_id: uuid.UUID,
    option_id: uuid.UUID,
    payload: PiGoalOptionDataUpdate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(
        session,
        update_goal_option(session, cycle, option_id, payload),
    )


@router.delete(
    "/pi-cycles/{cycle_id}/goal-options/{option_id}",
    response_model=PiCycleDataRead,
)
async def remove_pi_cycle_goal_option(
    cycle_id: uuid.UUID,
    option_id: uuid.UUID,
    payload: PiCycleDataCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, delete_goal_option(session, cycle, option_id))


@router.post("/pi-cycles/{cycle_id}/tags", response_model=PiCycleDataRead)
async def post_pi_cycle_tag(
    cycle_id: uuid.UUID,
    payload: PiTagDataCreate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, create_tag(session, cycle, payload))


@router.patch("/pi-cycles/{cycle_id}/tags/{tag_id}", response_model=PiCycleDataRead)
async def patch_pi_cycle_tag(
    cycle_id: uuid.UUID,
    tag_id: uuid.UUID,
    payload: PiTagDataUpdate,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, update_tag(session, cycle, tag_id, payload))


@router.delete("/pi-cycles/{cycle_id}/tags/{tag_id}", response_model=PiCycleDataRead)
async def remove_pi_cycle_tag(
    cycle_id: uuid.UUID,
    tag_id: uuid.UUID,
    payload: PiCycleDataCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_pi_data_command(session, delete_tag(session, cycle, tag_id))


@router.get("/pi-cycles/{cycle_id}/overview", response_model=OverviewRead)
async def pi_cycle_overview(cycle_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    cycle = await get_cycle_or_404(session, cycle_id)
    teams_count = await session.scalar(
        select(func.count())
        .select_from(PiCycleTeam)
        .where(PiCycleTeam.cycle_id == cycle_id)
    )
    backlog_count = await session.scalar(select(func.count()).select_from(BacklogItem))
    initiatives_count = await session.scalar(
        select(func.count()).select_from(Initiative).where(Initiative.cycle_id == cycle_id)
    )
    goals_count = await session.scalar(
        select(func.count()).select_from(PiGoal).where(PiGoal.cycle_id == cycle_id)
    )
    risks_count = await session.scalar(
        select(func.count()).select_from(Risk).where(Risk.cycle_id == cycle_id)
    )
    return OverviewRead(
        cycle=cycle,
        sprints=compute_sprints(cycle),
        teams_count=teams_count or 0,
        backlog_count=backlog_count or 0,
        initiatives_count=initiatives_count or 0,
        goals_count=goals_count or 0,
        risks_count=risks_count or 0,
    )


@router.get("/tribes", response_model=list[TribeRead])
async def list_tribes(session: AsyncSession = Depends(get_session)):
    result = await session.scalars(select(Tribe).order_by(Tribe.name))
    return result.all()


@router.post("/tribes", response_model=TribeRead, status_code=status.HTTP_201_CREATED)
async def create_tribe(payload: TribeCreate, session: AsyncSession = Depends(get_session)):
    existing = await session.scalar(select(Tribe).where(Tribe.name == payload.name))
    if existing:
        return existing
    tribe = Tribe(name=payload.name)
    session.add(tribe)
    await session.commit()
    await session.refresh(tribe)
    return tribe


@router.get("/teams", response_model=list[TeamRead])
async def list_teams(session: AsyncSession = Depends(get_session)):
    result = await session.scalars(select(Team).order_by(Team.name))
    return result.all()


@router.post("/teams", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(payload: TeamCreate, session: AsyncSession = Depends(get_session)):
    tribe = await session.get(Tribe, payload.tribe_id)
    if tribe is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Tribe not found",
        )
    existing = await session.scalar(
        select(Team).where(Team.tribe_id == payload.tribe_id, Team.name == payload.name.strip())
    )
    if existing is not None:
        return existing
    competencies = []
    for raw_code in payload.competencies:
        code = raw_code.strip().upper()
        if code and code not in competencies:
            competencies.append(code)
    if not competencies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one team competency is required",
        )
    team = Team(
        tribe_id=payload.tribe_id,
        name=payload.name.strip(),
        team_type=payload.team_type,
    )
    team.competencies = [
        TeamCompetency(code=code, sort_order=index)
        for index, code in enumerate(competencies)
    ]
    session.add(team)
    await session.commit()
    await session.refresh(team)
    return team


@router.post("/team-members", response_model=TeamMemberRead, status_code=status.HTTP_201_CREATED)
async def create_team_member(payload: TeamMemberCreate, session: AsyncSession = Depends(get_session)):
    if await session.get(Team, payload.team_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Team not found",
        )
    member = TeamMember(**payload.model_dump())
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


@router.get("/team-members", response_model=list[TeamMemberRead])
async def list_team_members(session: AsyncSession = Depends(get_session)):
    result = await session.scalars(select(TeamMember).order_by(TeamMember.full_name))
    return result.all()


async def _run_backlog_command(
    session: AsyncSession,
    operation,
    cycle_id: uuid.UUID | None = None,
):
    try:
        await operation
        await session.commit()
        return await read_backlog_board(session, cycle_id)
    except BacklogCascadeRequired as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.detail)
    except BacklogNotFound as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("/backlog-board", response_model=BacklogBoardRead)
async def get_backlog_board(
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    return await read_backlog_board(session, cycle_id)


@router.post(
    "/backlog-board/items",
    response_model=BacklogBoardRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_backlog_item(
    payload: BacklogItemCommand,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        create_backlog_item(session, payload, cycle_id),
        cycle_id,
    )


@router.patch("/backlog-board/items/{item_id}", response_model=BacklogBoardRead)
async def patch_backlog_item(
    item_id: uuid.UUID,
    payload: BacklogItemCommand,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        update_backlog_item(session, item_id, payload, cycle_id),
        cycle_id,
    )


@router.delete("/backlog-board/items/{item_id}", response_model=BacklogBoardRead)
async def delete_backlog_item_endpoint(
    item_id: uuid.UUID,
    payload: BacklogItemDelete,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        delete_backlog_item(session, item_id, payload),
        cycle_id,
    )


@router.put("/backlog-board/order", response_model=BacklogBoardRead)
async def put_backlog_order(
    payload: BacklogReorderCommand,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        reorder_backlog_items(session, payload),
        cycle_id,
    )


@router.put("/backlog-board", response_model=BacklogBoardRead)
async def put_backlog_board(
    payload: BacklogBoardWrite,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        replace_backlog_board(session, payload, cycle_id),
        cycle_id,
    )


@router.post("/backlog-board/dispatch", response_model=BacklogBoardRead)
async def dispatch_backlog(
    payload: BacklogDispatchWrite,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        dispatch_backlog_items(session, payload),
        cycle_id,
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Заполните обязательные поля Pre PI",
                "problems": error.problems,
            },
        )
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Issue ID must be unique inside a PI cycle",
        )
    _, _, competencies_by_team = await cycle_team_context(session, cycle.id)
    team_ids = [row.team_id for row in payload.executors]
    if len(team_ids) != len(set(team_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Executor team can only occur once",
        )
    if payload.owner_team_id is not None and payload.owner_team_id not in competencies_by_team:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Owner team is not part of this PI cycle",
        )
    normalized_executors = []
    try:
        for executor in payload.executors:
            if executor.team_id not in competencies_by_team:
                raise ValueError(f"Executor team is not part of this PI cycle: {executor.team_id}")
            normalized_executors.append(
                (
                    executor.team_id,
                    normalized_effort(
                        executor.effort_by_competency,
                        competencies_by_team[executor.team_id],
                        f"Initiative {payload.issue_key}",
                    ),
                )
            )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Goal team is not part of this PI cycle",
        )
    if payload.initiative_id is not None and not await session.scalar(
        select(Initiative).where(
            Initiative.cycle_id == cycle_id,
            Initiative.id == payload.initiative_id,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Goal initiative is not part of this PI cycle",
        )
    goal = PiGoal(cycle_id=cycle_id, **payload.model_dump())
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return goal


@router.get("/pi-cycles/{cycle_id}/risks", response_model=list[RiskRead])
async def list_risks(cycle_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    await get_cycle_or_404(session, cycle_id)
    result = await session.scalars(
        select(Risk).where(Risk.cycle_id == cycle_id).order_by(Risk.created_at.desc())
    )
    return result.all()


@router.get("/pi-cycles/{cycle_id}/risks-board", response_model=RisksRead)
async def get_risks_board(
    cycle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    cycle = await get_cycle_or_404(session, cycle_id)
    return await read_risks(session, cycle)


@router.put("/pi-cycles/{cycle_id}/risks-board", response_model=RisksRead)
async def put_risks_board(
    cycle_id: uuid.UUID,
    payload: RisksWrite,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await replace_risks(session, cycle, payload)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/pi-cycles/{cycle_id}/risks", response_model=RiskRead, status_code=status.HTTP_201_CREATED)
async def create_risk(
    cycle_id: uuid.UUID,
    payload: RiskCreate,
    session: AsyncSession = Depends(get_session),
):
    await lock_cycle(session, cycle_id)
    if payload.scope == "general" and (payload.team_id is not None or payload.is_shared):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A general risk cannot reference a team or be shared",
        )
    if payload.scope == "team":
        if payload.team_id is None or not await session.scalar(
            select(PiCycleTeam).where(
                PiCycleTeam.cycle_id == cycle_id,
                PiCycleTeam.team_id == payload.team_id,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Risk team is not part of this PI cycle",
            )
    risk_id = uuid.uuid4()
    risk = Risk(
        id=risk_id,
        cycle_id=cycle_id,
        client_uid=f"risk-{risk_id}",
        **payload.model_dump(),
    )
    session.add(risk)
    await session.commit()
    await session.refresh(risk)
    return risk
