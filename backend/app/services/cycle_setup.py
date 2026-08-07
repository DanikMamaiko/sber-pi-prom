from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    Initiative,
    InitiativeExecutor,
    PiCycle,
    PiCycleCapacityMember,
    PiCycleGoalOption,
    PiCycleTag,
    PiCycleTeam,
    PiCycleTeamCompetency,
    PiEvent,
    PiGoal,
    Risk,
    Team,
    Tribe,
)
from app.schemas.pi_cycle import PiCycleSetupRead, PiCycleSetupWrite
from app.schemas.pi_cycle_data import EVENT_TYPE_PIR, EVENT_TYPE_REGRESSION


def _unique_non_empty(values: list[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = raw.strip()
        if value and value not in result:
            result.append(value)
    return result


async def read_cycle_setup(session: AsyncSession, cycle: PiCycle) -> PiCycleSetupRead:
    events = (
        await session.scalars(
            select(PiEvent)
            .where(PiEvent.cycle_id == cycle.id)
            .order_by(PiEvent.sort_order, PiEvent.id)
        )
    ).all()
    cycle_teams = (
        await session.scalars(
            select(PiCycleTeam)
            .options(
                selectinload(PiCycleTeam.team).selectinload(Team.tribe),
                selectinload(PiCycleTeam.competencies),
            )
            .where(PiCycleTeam.cycle_id == cycle.id)
            .order_by(PiCycleTeam.sort_order, PiCycleTeam.id)
        )
    ).all()
    goals = (
        await session.scalars(
            select(PiCycleGoalOption)
            .where(PiCycleGoalOption.cycle_id == cycle.id)
            .order_by(PiCycleGoalOption.sort_order, PiCycleGoalOption.id)
        )
    ).all()
    tags = (
        await session.scalars(
            select(PiCycleTag)
            .where(PiCycleTag.cycle_id == cycle.id)
            .order_by(PiCycleTag.sort_order, PiCycleTag.id)
        )
    ).all()

    return PiCycleSetupRead(
        initialized=cycle.setup_initialized,
        version=cycle.version,
        start_date=cycle.start_date,
        sprint_count=cycle.sprint_count,
        pirs=[
            {"name": event.name, "date": event.event_date, "end_date": event.event_end_date}
            for event in events
            if event.event_type == EVENT_TYPE_PIR
        ],
        regressions=[
            {"name": event.name, "date": event.event_date, "end_date": event.event_end_date}
            for event in events
            if event.event_type == EVENT_TYPE_REGRESSION
        ],
        teams=[
            {
                "tribe": item.team.tribe.name,
                "name": item.team.name,
                "team_type": item.team_type,
                "excluded_from_goals": item.excluded_from_goals,
                "competencies": [competency.code for competency in item.competencies],
            }
            for item in cycle_teams
        ],
        goals=[goal.name for goal in goals],
        tags=[tag.name for tag in tags],
    )


async def replace_cycle_setup(
    session: AsyncSession,
    cycle: PiCycle,
    payload: PiCycleSetupWrite,
) -> PiCycleSetupRead:
    team_keys = [
        (item.tribe.strip().casefold(), item.name.strip().casefold())
        for item in payload.teams
    ]
    if len(team_keys) != len(set(team_keys)):
        raise ValueError("Команда может входить в PI-цикл только один раз")
    for item in payload.teams:
        if not item.tribe.strip() or not item.name.strip():
            raise ValueError("Укажите трайб и название команды")
        if item.team_type not in {"Agile", "ИТ-проект"}:
            raise ValueError(f"Неподдерживаемый тип команды: {item.team_type}")
        competencies = _unique_non_empty([value.upper() for value in item.competencies])
        if any(len(code) > 32 for code in competencies):
            raise ValueError(f"Код компетенции слишком длинный для команды: {item.name}")
    if any(not event.name.strip() for event in payload.pirs):
        raise ValueError("Название ПИР не может быть пустым")
    if any(not event.name.strip() for event in payload.regressions):
        raise ValueError("Название регрессии не может быть пустым")

    cycle.start_date = payload.start_date
    cycle.sprint_count = payload.sprint_count
    cycle.setup_initialized = True

    await session.execute(delete(PiEvent).where(PiEvent.cycle_id == cycle.id))
    await session.execute(delete(PiCycleTeam).where(PiCycleTeam.cycle_id == cycle.id))
    await session.execute(
        delete(PiCycleGoalOption).where(PiCycleGoalOption.cycle_id == cycle.id)
    )
    await session.execute(delete(PiCycleTag).where(PiCycleTag.cycle_id == cycle.id))

    for index, event in enumerate(payload.pirs):
        session.add(
            PiEvent(
                cycle_id=cycle.id,
                name=event.name.strip(),
                event_date=event.date,
                event_end_date=event.end_date,
                event_type=EVENT_TYPE_PIR,
                sort_order=index,
            )
        )
    for index, event in enumerate(payload.regressions):
        session.add(
            PiEvent(
                cycle_id=cycle.id,
                name=event.name.strip(),
                event_date=event.date,
                event_end_date=event.end_date,
                event_type=EVENT_TYPE_REGRESSION,
                sort_order=index,
            )
        )

    tribe_cache: dict[str, Tribe] = {}
    selected_team_ids = []
    for index, item in enumerate(payload.teams):
        tribe_name = item.tribe.strip()
        team_name = item.name.strip()
        tribe = tribe_cache.get(tribe_name)
        if tribe is None:
            tribe = await session.scalar(select(Tribe).where(Tribe.name == tribe_name))
            if tribe is None:
                tribe = Tribe(name=tribe_name)
                session.add(tribe)
                await session.flush()
            tribe_cache[tribe_name] = tribe

        team = await session.scalar(
            select(Team).where(Team.tribe_id == tribe.id, Team.name == team_name)
        )
        if team is None:
            team = Team(tribe_id=tribe.id, name=team_name)
            session.add(team)
            await session.flush()
        team.team_type = item.team_type
        team.excluded_from_goals = item.excluded_from_goals
        selected_team_ids.append(team.id)

        cycle_team = PiCycleTeam(
            cycle_id=cycle.id,
            team_id=team.id,
            team_type=item.team_type,
            excluded_from_goals=item.excluded_from_goals,
            sort_order=index,
        )
        cycle_team.competencies = [
            PiCycleTeamCompetency(code=code, sort_order=competency_index)
            for competency_index, code in enumerate(
                _unique_non_empty([value.upper() for value in item.competencies])
            )
        ]
        session.add(cycle_team)

    capacity_delete = delete(PiCycleCapacityMember).where(
        PiCycleCapacityMember.cycle_id == cycle.id
    )
    if selected_team_ids:
        capacity_delete = capacity_delete.where(
            PiCycleCapacityMember.team_id.not_in(selected_team_ids)
        )
    await session.execute(capacity_delete)

    team_risks_delete = delete(Risk).where(
        Risk.cycle_id == cycle.id,
        Risk.scope == "team",
    )
    if selected_team_ids:
        team_risks_delete = team_risks_delete.where(Risk.team_id.not_in(selected_team_ids))
    await session.execute(team_risks_delete)

    removed_executor_delete = delete(InitiativeExecutor).where(
        InitiativeExecutor.initiative_id.in_(
            select(Initiative.id).where(Initiative.cycle_id == cycle.id)
        )
    )
    removed_owner_update = (
        Initiative.__table__.update().where(Initiative.cycle_id == cycle.id)
    )
    removed_goal_delete = delete(PiGoal).where(PiGoal.cycle_id == cycle.id)
    if selected_team_ids:
        removed_executor_delete = removed_executor_delete.where(
            InitiativeExecutor.team_id.not_in(selected_team_ids)
        )
        removed_owner_update = removed_owner_update.where(
            Initiative.owner_team_id.not_in(selected_team_ids)
        )
        removed_goal_delete = removed_goal_delete.where(
            PiGoal.team_id.is_not(None),
            PiGoal.team_id.not_in(selected_team_ids),
        )
    await session.execute(removed_executor_delete)
    await session.execute(removed_owner_update.values(owner_team_id=None))
    await session.execute(removed_goal_delete)

    for index, name in enumerate(_unique_non_empty(payload.goals)):
        session.add(PiCycleGoalOption(cycle_id=cycle.id, name=name, sort_order=index))
    for index, name in enumerate(_unique_non_empty(payload.tags)):
        session.add(PiCycleTag(cycle_id=cycle.id, name=name, sort_order=index))

    await session.commit()
    await session.refresh(cycle)
    return await read_cycle_setup(session, cycle)
