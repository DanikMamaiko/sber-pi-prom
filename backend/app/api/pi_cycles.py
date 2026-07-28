import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.pi_cycle import (
    BacklogExecutor,
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
    BacklogDispatchRead,
    BacklogDispatchWrite,
    BacklogItemCreate,
    BacklogItemRead,
    CapacityRead,
    CapacityWrite,
    GoalsRead,
    GoalsWrite,
    InitiativeCreate,
    InitiativeRead,
    OverviewRead,
    PiCycleCreate,
    PiCycleRead,
    PiCycleSetupRead,
    PiCycleSetupWrite,
    PiCycleUpdate,
    PrePiRead,
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
    dispatch_backlog_items,
    read_backlog_board,
    replace_backlog_board,
)
from app.services.pre_pi import read_pre_pi, replace_pre_pi
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
    session.add(cycle)
    await session.commit()
    await session.refresh(cycle)
    return cycle


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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


@router.get("/backlog", response_model=list[BacklogItemRead])
async def list_backlog(session: AsyncSession = Depends(get_session)):
    result = await session.scalars(select(BacklogItem).order_by(BacklogItem.created_at.desc()))
    return result.all()


@router.post("/backlog", response_model=BacklogItemRead, status_code=status.HTTP_201_CREATED)
async def create_backlog_item(payload: BacklogItemCreate, session: AsyncSession = Depends(get_session)):
    await lock_backlog(session)
    if await session.scalar(
        select(BacklogItem).where(func.lower(BacklogItem.issue_key) == payload.issue_key.strip().lower())
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Issue ID must be unique across the global backlog",
        )
    executor_team_ids = [row.team_id for row in payload.executors]
    if len(executor_team_ids) != len(set(executor_team_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Executor team can only occur once",
        )
    for executor in payload.executors:
        if await session.get(Team, executor.team_id) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Executor team not found: {executor.team_id}",
            )
    data = payload.model_dump(exclude={"executors"})
    data["issue_key"] = payload.issue_key.strip()
    item = BacklogItem(**data)
    item.executors = [
        BacklogExecutor(team_id=executor.team_id, effort_by_competency=executor.effort_by_competency)
        for executor in payload.executors
    ]
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/backlog-board", response_model=BacklogBoardRead)
async def get_backlog_board(session: AsyncSession = Depends(get_session)):
    return await read_backlog_board(session)


@router.put("/backlog-board", response_model=BacklogBoardRead)
async def put_backlog_board(
    payload: BacklogBoardWrite,
    session: AsyncSession = Depends(get_session),
):
    try:
        await lock_backlog(session, payload.expected_version)
        return await replace_backlog_board(session, payload)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


@router.post(
    "/pi-cycles/{cycle_id}/backlog/dispatch",
    response_model=BacklogDispatchRead,
)
async def dispatch_backlog_to_cycle(
    cycle_id: uuid.UUID,
    payload: BacklogDispatchWrite,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await dispatch_backlog_items(session, cycle, payload)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Заполните обязательные поля Pre PI",
                "problems": error.problems,
            },
        )
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Issue ID must be unique inside a PI cycle",
        )
    _, _, competencies_by_team = await cycle_team_context(session, cycle.id)
    team_ids = [row.team_id for row in payload.executors]
    if len(team_ids) != len(set(team_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Executor team can only occur once",
        )
    if payload.owner_team_id is not None and payload.owner_team_id not in competencies_by_team:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))
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


@router.post(
    "/pi-cycles/{cycle_id}/initiatives/from-backlog/{backlog_item_id}",
    response_model=InitiativeRead,
)
async def move_backlog_item_to_cycle(
    cycle_id: uuid.UUID,
    backlog_item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id)
    try:
        result = await dispatch_backlog_items(
            session,
            cycle,
            BacklogDispatchWrite(
                expected_version=cycle.version - 1,
                backlog_item_ids=[backlog_item_id],
            ),
        )
    except ValueError as error:
        await session.rollback()
        detail = str(error)
        if detail.startswith("Backlog items not found"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backlog item not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    return result.initiatives[0]


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Goal team is not part of this PI cycle",
        )
    if payload.initiative_id is not None and not await session.scalar(
        select(Initiative).where(
            Initiative.cycle_id == cycle_id,
            Initiative.id == payload.initiative_id,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


@router.post("/pi-cycles/{cycle_id}/risks", response_model=RiskRead, status_code=status.HTTP_201_CREATED)
async def create_risk(
    cycle_id: uuid.UUID,
    payload: RiskCreate,
    session: AsyncSession = Depends(get_session),
):
    await lock_cycle(session, cycle_id)
    if payload.scope == "general" and (payload.team_id is not None or payload.is_shared):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
