import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.auth.dependencies import require_http_permission
from app.auth.permissions import Permission
from app.db.session import get_session
from app.models.pi_cycle import (
    BacklogItem,
    Initiative,
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
    OverviewRead,
    PiCycleCreate,
    PiCycleDataCommand,
    PiCycleDataRead,
    PiCycleDataReplace,
    PiCycleDataUpdate,
    PiCycleRead,
    PiCycleSetupRead,
    PiCycleSetupWrite,
    PiCycleTeamDataCreate,
    PiCycleTeamDataUpdate,
    PiCycleTeamDelete,
    PiCycleUpdate,
    PiEventDataCreate,
    PiEventDataUpdate,
    PiGoalOptionDataCreate,
    PiGoalOptionDataUpdate,
    PiTagDataCreate,
    PiTagDataUpdate,
    TeamCreate,
    TeamMemberCreate,
    TeamMemberRead,
    TeamRead,
    TribeCreate,
    TribeRead,
)
from app.services.cycle_setup import read_cycle_setup, replace_cycle_setup
from app.services.optimistic_locking import lock_cycle
from app.services.planning import compute_sprints
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

router = APIRouter(
    tags=["PI Cycle"],
    dependencies=[Depends(require_http_permission(Permission.PI_DATA_READ, Permission.PI_DATA_WRITE))],
)


async def _run_pi_data_command(session: AsyncSession, operation):
    try:
        return await operation
    except CascadeRequired as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.detail)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error))


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
        raise HTTPException(status_code=422, detail=str(error))


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
            status_code=422,
            detail="Трайб не найден",
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
            status_code=422,
            detail="Требуется хотя бы одна компетенция команды",
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
            status_code=422,
            detail="Команда не найдена",
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


