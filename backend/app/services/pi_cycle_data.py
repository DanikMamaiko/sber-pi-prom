import uuid
from datetime import timedelta

from sqlalchemy import delete, func, select, update
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
    Story,
    Team,
    Tribe,
    WorkItem,
)
from app.schemas.pi_cycle import (
    PiCycleDataReplace,
    PiCycleDataRead,
    PiCycleDataUpdate,
    PiCycleTeamDataCreate,
    PiCycleTeamDataUpdate,
    PiCycleTeamDelete,
    PiEventDataCreate,
    PiEventDataUpdate,
    PiGoalOptionDataCreate,
    PiGoalOptionDataUpdate,
    PiTagDataCreate,
    PiTagDataUpdate,
)
from app.services.planning import compute_sprints, workdays_between
from app.services.program_board import delete_dangling_connections


TEAM_TYPES = ["Agile", "ИТ-проект"]
COMPETENCIES = ["SA", "DEV", "QA", "FE", "BE", "DES"]


class CascadeRequired(ValueError):
    def __init__(self, entity: str, affected: dict[str, int]):
        self.detail = {
            "code": "cascade_confirmation_required",
            "entity": entity,
            "affected": affected,
        }
        super().__init__("Cascade confirmation is required")


def _clean_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip().upper()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _cycle_end(cycle: PiCycle):
    if cycle.start_date is None:
        return None
    return cycle.start_date + timedelta(days=cycle.sprint_count * 14 - 1)


def _validate_event_date(cycle: PiCycle, value) -> None:
    end_date = _cycle_end(cycle)
    if cycle.start_date is None or end_date is None:
        raise ValueError("PI start date must be set before adding a PIR")
    if value < cycle.start_date or value > end_date:
        raise ValueError(
            f"PIR date must be between {cycle.start_date.isoformat()} and {end_date.isoformat()}"
        )


async def _data_rows(session: AsyncSession, cycle_id: uuid.UUID):
    events = list(
        (
            await session.scalars(
                select(PiEvent)
                .where(PiEvent.cycle_id == cycle_id)
                .order_by(PiEvent.sort_order, PiEvent.id)
            )
        ).all()
    )
    teams = list(
        (
            await session.scalars(
                select(PiCycleTeam)
                .options(
                    selectinload(PiCycleTeam.team).selectinload(Team.tribe),
                    selectinload(PiCycleTeam.competencies),
                )
                .where(PiCycleTeam.cycle_id == cycle_id)
                .order_by(PiCycleTeam.sort_order, PiCycleTeam.id)
            )
        ).all()
    )
    goals = list(
        (
            await session.scalars(
                select(PiCycleGoalOption)
                .where(PiCycleGoalOption.cycle_id == cycle_id)
                .order_by(PiCycleGoalOption.sort_order, PiCycleGoalOption.id)
            )
        ).all()
    )
    tags = list(
        (
            await session.scalars(
                select(PiCycleTag)
                .where(PiCycleTag.cycle_id == cycle_id)
                .order_by(PiCycleTag.sort_order, PiCycleTag.id)
            )
        ).all()
    )
    return events, teams, goals, tags


async def read_pi_cycle_data(
    session: AsyncSession,
    cycle: PiCycle,
) -> PiCycleDataRead:
    events, teams, goals, tags = await _data_rows(session, cycle.id)
    event_rows = [
        {
            "id": row.id,
            "name": row.name,
            "date": row.event_date,
            "sort_order": row.sort_order,
        }
        for row in events
    ]
    sprints = []
    total_workdays = 0
    for sprint in compute_sprints(cycle):
        workdays = workdays_between(sprint.start_date, sprint.end_date)
        total_workdays += workdays
        first_week_end = sprint.start_date + timedelta(days=6)
        weeks = [
            {
                "index": 0,
                "start_date": sprint.start_date,
                "end_date": first_week_end,
                "workdays": workdays_between(sprint.start_date, first_week_end),
            },
            {
                "index": 1,
                "start_date": first_week_end + timedelta(days=1),
                "end_date": sprint.end_date,
                "workdays": workdays_between(first_week_end + timedelta(days=1), sprint.end_date),
            },
        ]
        sprint_events = [
            row
            for row in event_rows
            if sprint.start_date <= row["date"] <= sprint.end_date
        ]
        sprints.append(
            {
                "index": sprint.index,
                "title": sprint.title,
                "start_date": sprint.start_date,
                "end_date": sprint.end_date,
                "workdays": workdays,
                "weeks": weeks,
                "pirs": sprint_events,
            }
        )

    return PiCycleDataRead(
        cycle=cycle,
        schedule={
            "end_date": _cycle_end(cycle),
            "total_workdays": total_workdays,
            "sprints": sprints,
        },
        pirs=event_rows,
        teams=[
            {
                "id": row.id,
                "team_id": row.team_id,
                "tribe_id": row.team.tribe_id,
                "tribe": row.team.tribe.name,
                "name": row.team.name,
                "team_type": row.team_type,
                "excluded_from_goals": row.excluded_from_goals,
                "competencies": [item.code for item in row.competencies],
                "sort_order": row.sort_order,
            }
            for row in teams
        ],
        goal_options=[
            {"id": row.id, "name": row.name, "sort_order": row.sort_order}
            for row in goals
        ],
        tags=[
            {"id": row.id, "name": row.name, "sort_order": row.sort_order}
            for row in tags
        ],
        reference_data={
            "team_types": TEAM_TYPES,
            "competencies": COMPETENCIES,
            "sprint_count_min": 1,
            "sprint_count_max": 20,
        },
    )


async def _commit_data(session: AsyncSession, cycle: PiCycle) -> PiCycleDataRead:
    cycle.setup_initialized = True
    await session.commit()
    await session.refresh(cycle)
    return await read_pi_cycle_data(session, cycle)


async def _finish_data(
    session: AsyncSession,
    cycle: PiCycle,
    *,
    commit: bool,
) -> PiCycleDataRead | None:
    if commit:
        return await _commit_data(session, cycle)
    cycle.setup_initialized = True
    await session.flush()
    return None


async def update_cycle_data(
    session: AsyncSession,
    cycle: PiCycle,
    payload: PiCycleDataUpdate,
    *,
    commit: bool = True,
    validate_events: bool = True,
) -> PiCycleDataRead:
    out_of_range = {
        "initiatives": int(
            await session.scalar(
                select(func.count())
                .select_from(Initiative)
                .where(Initiative.cycle_id == cycle.id, Initiative.sprint_index >= payload.sprint_count)
            )
            or 0
        ),
        "stories": int(
            await session.scalar(
                select(func.count())
                .select_from(Story)
                .join(Initiative, Initiative.id == Story.initiative_id)
                .where(Initiative.cycle_id == cycle.id, Story.sprint_index >= payload.sprint_count)
            )
            or 0
        ),
        "work_items": int(
            await session.scalar(
                select(func.count())
                .select_from(WorkItem)
                .join(Initiative, Initiative.id == WorkItem.initiative_id)
                .where(Initiative.cycle_id == cycle.id, WorkItem.sprint_index >= payload.sprint_count)
            )
            or 0
        ),
    }
    if any(out_of_range.values()) and payload.cascade_policy != "unassign_out_of_range":
        raise CascadeRequired("pi_schedule", out_of_range)
    if any(out_of_range.values()):
        await session.execute(
            update(Initiative)
            .where(Initiative.cycle_id == cycle.id, Initiative.sprint_index >= payload.sprint_count)
            .values(sprint_index=None, week_index=None, agreed=False)
        )
        await session.execute(
            update(Story)
            .where(
                Story.initiative_id.in_(
                    select(Initiative.id).where(Initiative.cycle_id == cycle.id)
                ),
                Story.sprint_index >= payload.sprint_count,
            )
            .values(sprint_index=None, week_index=None)
        )
        await session.execute(
            update(WorkItem)
            .where(
                WorkItem.initiative_id.in_(
                    select(Initiative.id).where(Initiative.cycle_id == cycle.id)
                ),
                WorkItem.sprint_index >= payload.sprint_count,
            )
            .values(sprint_index=None, week_index=None)
        )
    cycle.start_date = payload.start_date
    cycle.sprint_count = payload.sprint_count
    if validate_events:
        events = (
            await session.scalars(select(PiEvent).where(PiEvent.cycle_id == cycle.id))
        ).all()
        for event in events:
            _validate_event_date(cycle, event.event_date)
    return await _finish_data(session, cycle, commit=commit)


async def _next_order(session: AsyncSession, model, cycle_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(model.sort_order)).where(model.cycle_id == cycle_id)
    )
    return int(current if current is not None else -1) + 1


async def create_pir(
    session: AsyncSession,
    cycle: PiCycle,
    payload: PiEventDataCreate,
    *,
    commit: bool = True,
):
    name = payload.name.strip()
    _validate_event_date(cycle, payload.date)
    if await session.scalar(
        select(PiEvent).where(
            PiEvent.cycle_id == cycle.id,
            func.lower(PiEvent.name) == name.casefold(),
        )
    ):
        raise ValueError("PIR name must be unique inside a PI cycle")
    session.add(
        PiEvent(
            cycle_id=cycle.id,
            name=name,
            event_date=payload.date,
            sort_order=await _next_order(session, PiEvent, cycle.id),
        )
    )
    return await _finish_data(session, cycle, commit=commit)


async def update_pir(
    session: AsyncSession,
    cycle: PiCycle,
    event_id: uuid.UUID,
    payload: PiEventDataUpdate,
    *,
    commit: bool = True,
):
    event = await session.scalar(
        select(PiEvent).where(PiEvent.id == event_id, PiEvent.cycle_id == cycle.id)
    )
    if event is None:
        raise ValueError("PIR not found in this PI cycle")
    name = payload.name.strip()
    _validate_event_date(cycle, payload.date)
    duplicate = await session.scalar(
        select(PiEvent).where(
            PiEvent.cycle_id == cycle.id,
            PiEvent.id != event.id,
            func.lower(PiEvent.name) == name.casefold(),
        )
    )
    if duplicate:
        raise ValueError("PIR name must be unique inside a PI cycle")
    event.name = name
    event.event_date = payload.date
    return await _finish_data(session, cycle, commit=commit)


async def delete_pir(
    session: AsyncSession,
    cycle: PiCycle,
    event_id: uuid.UUID,
    *,
    commit: bool = True,
):
    event = await session.scalar(
        select(PiEvent).where(PiEvent.id == event_id, PiEvent.cycle_id == cycle.id)
    )
    if event is None:
        raise ValueError("PIR not found in this PI cycle")
    await session.delete(event)
    return await _finish_data(session, cycle, commit=commit)


async def _resolve_tribe_team(
    session: AsyncSession,
    tribe_name: str,
    team_name: str,
) -> tuple[Tribe, Team]:
    clean_tribe = tribe_name.strip()
    clean_team = team_name.strip()
    tribe = await session.scalar(
        select(Tribe).where(func.lower(Tribe.name) == clean_tribe.casefold())
    )
    if tribe is None:
        tribe = Tribe(name=clean_tribe)
        session.add(tribe)
        await session.flush()
    team = await session.scalar(
        select(Team).where(
            Team.tribe_id == tribe.id,
            func.lower(Team.name) == clean_team.casefold(),
        )
    )
    if team is None:
        team = Team(tribe_id=tribe.id, name=clean_team)
        session.add(team)
        await session.flush()
    return tribe, team


def _validate_team_payload(payload) -> list[str]:
    competencies = _clean_unique(payload.competencies)
    unknown = [code for code in competencies if code not in COMPETENCIES]
    if unknown:
        raise ValueError(f"Unsupported competencies: {', '.join(unknown)}")
    if not competencies:
        raise ValueError("At least one competency is required")
    return competencies


async def create_cycle_team(
    session: AsyncSession,
    cycle: PiCycle,
    payload: PiCycleTeamDataCreate,
    *,
    commit: bool = True,
):
    competencies = _validate_team_payload(payload)
    _, team = await _resolve_tribe_team(session, payload.tribe, payload.name)
    if await session.scalar(
        select(PiCycleTeam).where(
            PiCycleTeam.cycle_id == cycle.id,
            PiCycleTeam.team_id == team.id,
        )
    ):
        raise ValueError("Team is already included in this PI cycle")
    row = PiCycleTeam(
        cycle_id=cycle.id,
        team_id=team.id,
        team_type=payload.team_type,
        excluded_from_goals=payload.excluded_from_goals,
        sort_order=await _next_order(session, PiCycleTeam, cycle.id),
    )
    row.competencies = [
        PiCycleTeamCompetency(code=code, sort_order=index)
        for index, code in enumerate(competencies)
    ]
    session.add(row)
    return await _finish_data(session, cycle, commit=commit)


async def _replace_attraction_team(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    old_name: str,
    new_name: str | None,
) -> None:
    executors = list(
        (
            await session.scalars(
                select(InitiativeExecutor)
                .join(Initiative, Initiative.id == InitiativeExecutor.initiative_id)
                .where(Initiative.cycle_id == cycle_id)
            )
        ).all()
    )
    for executor in executors:
        changed = False
        next_rows = []
        for attraction in list(executor.attractions or []):
            row = dict(attraction)
            if str(row.get("team") or "").strip().casefold() == old_name.casefold():
                changed = True
                if new_name is None:
                    continue
                row["team"] = new_name
            next_rows.append(row)
        if changed:
            executor.attractions = next_rows


async def update_cycle_team(
    session: AsyncSession,
    cycle: PiCycle,
    cycle_team_id: uuid.UUID,
    payload: PiCycleTeamDataUpdate,
    *,
    commit: bool = True,
):
    row = await session.scalar(
        select(PiCycleTeam)
        .options(
            selectinload(PiCycleTeam.team).selectinload(Team.tribe),
            selectinload(PiCycleTeam.competencies),
        )
        .where(PiCycleTeam.id == cycle_team_id, PiCycleTeam.cycle_id == cycle.id)
    )
    if row is None:
        raise ValueError("Team is not included in this PI cycle")
    competencies = _validate_team_payload(payload)
    old_team = row.team
    _, target_team = await _resolve_tribe_team(session, payload.tribe, payload.name)
    if target_team.id != old_team.id:
        duplicate_membership = await session.scalar(
            select(PiCycleTeam).where(
                PiCycleTeam.cycle_id == cycle.id,
                PiCycleTeam.team_id == target_team.id,
                PiCycleTeam.id != row.id,
            )
        )
        if duplicate_membership:
            raise ValueError("Target team is already included in this PI cycle")
        initiative_ids = list(
            (
                await session.scalars(
                    select(InitiativeExecutor.initiative_id)
                    .join(Initiative, Initiative.id == InitiativeExecutor.initiative_id)
                    .where(
                        Initiative.cycle_id == cycle.id,
                        InitiativeExecutor.team_id == old_team.id,
                    )
                )
            ).all()
        )
        if initiative_ids and await session.scalar(
            select(InitiativeExecutor).where(
                InitiativeExecutor.initiative_id.in_(initiative_ids),
                InitiativeExecutor.team_id == target_team.id,
            )
        ):
            raise ValueError("An initiative already contains the target team as executor")
        await session.execute(
            update(Initiative)
            .where(Initiative.cycle_id == cycle.id, Initiative.owner_team_id == old_team.id)
            .values(owner_team_id=target_team.id)
        )
        await session.execute(
            update(InitiativeExecutor)
            .where(
                InitiativeExecutor.initiative_id.in_(
                    select(Initiative.id).where(Initiative.cycle_id == cycle.id)
                ),
                InitiativeExecutor.team_id == old_team.id,
            )
            .values(team_id=target_team.id)
        )
        await session.execute(
            update(PiCycleCapacityMember)
            .where(
                PiCycleCapacityMember.cycle_id == cycle.id,
                PiCycleCapacityMember.team_id == old_team.id,
            )
            .values(team_id=target_team.id)
        )
        await session.execute(
            update(PiGoal)
            .where(PiGoal.cycle_id == cycle.id, PiGoal.team_id == old_team.id)
            .values(team_id=target_team.id, tribe_id=target_team.tribe_id)
        )
        await session.execute(
            update(Risk)
            .where(Risk.cycle_id == cycle.id, Risk.team_id == old_team.id)
            .values(team_id=target_team.id)
        )
        await _replace_attraction_team(session, cycle.id, old_team.name, target_team.name)
        row.team = target_team

    removed = {item.code for item in row.competencies} - set(competencies)
    if removed:
        executor_rows = list(
            (
                await session.scalars(
                    select(InitiativeExecutor)
                    .join(Initiative, Initiative.id == InitiativeExecutor.initiative_id)
                    .where(
                        Initiative.cycle_id == cycle.id,
                        InitiativeExecutor.team_id == target_team.id,
                    )
                )
            ).all()
        )
        initiative_ids = [item.initiative_id for item in executor_rows]
        capacity_rows = list(
            (
                await session.scalars(
                    select(PiCycleCapacityMember).where(
                        PiCycleCapacityMember.cycle_id == cycle.id,
                        PiCycleCapacityMember.team_id == target_team.id,
                        PiCycleCapacityMember.competency.in_(removed),
                    )
                )
            ).all()
        )
        work_rows = []
        story_rows = []
        if initiative_ids:
            work_rows = list(
                (
                    await session.scalars(
                        select(WorkItem).where(
                            WorkItem.initiative_id.in_(initiative_ids),
                            WorkItem.competency.in_(removed),
                        )
                    )
                ).all()
            )
            story_rows = list(
                (
                    await session.scalars(
                        select(Story).where(Story.initiative_id.in_(initiative_ids))
                    )
                ).all()
            )
        executor_effort = sum(
            1
            for item in executor_rows
            if any(code in (item.effort_by_competency or {}) for code in removed)
        )
        story_effort = sum(
            1
            for item in story_rows
            if any(code in (item.effort_by_competency or {}) for code in removed)
        )
        affected = {
            "executor_effort": executor_effort,
            "story_effort": story_effort,
            "capacity_members": len(capacity_rows),
            "work_items": len(work_rows),
        }
        if any(affected.values()) and payload.cascade_policy != "remove_competency_usage":
            raise CascadeRequired("team_competency", affected)
        for item in executor_rows:
            item.effort_by_competency = {
                code: value
                for code, value in (item.effort_by_competency or {}).items()
                if code not in removed
            }
        for item in story_rows:
            item.effort_by_competency = {
                code: value
                for code, value in (item.effort_by_competency or {}).items()
                if code not in removed
            }
        for item in capacity_rows:
            await session.delete(item)
        for item in work_rows:
            await session.delete(item)
        await session.flush()
        await delete_dangling_connections(session, cycle.id)

    row.team_type = payload.team_type
    row.excluded_from_goals = payload.excluded_from_goals
    row.competencies.clear()
    await session.flush()
    row.competencies = [
        PiCycleTeamCompetency(code=code, sort_order=index)
        for index, code in enumerate(competencies)
    ]
    return await _finish_data(session, cycle, commit=commit)


async def delete_cycle_team(
    session: AsyncSession,
    cycle: PiCycle,
    cycle_team_id: uuid.UUID,
    payload: PiCycleTeamDelete,
    *,
    commit: bool = True,
):
    row = await session.scalar(
        select(PiCycleTeam)
        .options(selectinload(PiCycleTeam.team))
        .where(PiCycleTeam.id == cycle_team_id, PiCycleTeam.cycle_id == cycle.id)
    )
    if row is None:
        raise ValueError("Team is not included in this PI cycle")
    team_id = row.team_id
    affected = {
        "owners": int(
            await session.scalar(
                select(func.count()).select_from(Initiative).where(
                    Initiative.cycle_id == cycle.id, Initiative.owner_team_id == team_id
                )
            )
            or 0
        ),
        "executors": int(
            await session.scalar(
                select(func.count())
                .select_from(InitiativeExecutor)
                .join(Initiative, Initiative.id == InitiativeExecutor.initiative_id)
                .where(Initiative.cycle_id == cycle.id, InitiativeExecutor.team_id == team_id)
            )
            or 0
        ),
        "goals": int(
            await session.scalar(
                select(func.count()).select_from(PiGoal).where(
                    PiGoal.cycle_id == cycle.id, PiGoal.team_id == team_id
                )
            )
            or 0
        ),
        "capacity_members": int(
            await session.scalar(
                select(func.count()).select_from(PiCycleCapacityMember).where(
                    PiCycleCapacityMember.cycle_id == cycle.id,
                    PiCycleCapacityMember.team_id == team_id,
                )
            )
            or 0
        ),
        "risks": int(
            await session.scalar(
                select(func.count()).select_from(Risk).where(
                    Risk.cycle_id == cycle.id, Risk.team_id == team_id
                )
            )
            or 0
        ),
    }
    if any(affected.values()) and not payload.confirm_cascade:
        raise CascadeRequired("cycle_team", affected)
    impacted_ids = list(
        (
            await session.scalars(
                select(InitiativeExecutor.initiative_id)
                .join(Initiative, Initiative.id == InitiativeExecutor.initiative_id)
                .where(Initiative.cycle_id == cycle.id, InitiativeExecutor.team_id == team_id)
            )
        ).all()
    )
    await _replace_attraction_team(session, cycle.id, row.team.name, None)
    await session.execute(
        delete(PiCycleCapacityMember).where(
            PiCycleCapacityMember.cycle_id == cycle.id,
            PiCycleCapacityMember.team_id == team_id,
        )
    )
    await session.execute(
        delete(Risk).where(Risk.cycle_id == cycle.id, Risk.team_id == team_id)
    )
    await session.execute(
        delete(PiGoal).where(PiGoal.cycle_id == cycle.id, PiGoal.team_id == team_id)
    )
    await session.execute(
        delete(InitiativeExecutor).where(
            InitiativeExecutor.initiative_id.in_(
                select(Initiative.id).where(Initiative.cycle_id == cycle.id)
            ),
            InitiativeExecutor.team_id == team_id,
        )
    )
    await session.execute(
        update(Initiative)
        .where(Initiative.cycle_id == cycle.id, Initiative.owner_team_id == team_id)
        .values(owner_team_id=None)
    )
    await session.flush()
    for initiative_id in set(impacted_ids):
        remaining = int(
            await session.scalar(
                select(func.count()).select_from(InitiativeExecutor).where(
                    InitiativeExecutor.initiative_id == initiative_id
                )
            )
            or 0
        )
        if remaining == 0:
            await session.execute(
                update(Initiative)
                .where(Initiative.id == initiative_id)
                .values(
                    status="backlog",
                    pre_planned=False,
                    on_board=False,
                    agreed=False,
                    sprint_index=None,
                    week_index=None,
                )
            )
            await session.execute(delete(Story).where(Story.initiative_id == initiative_id))
            await session.execute(delete(WorkItem).where(WorkItem.initiative_id == initiative_id))
    await session.delete(row)
    await session.flush()
    await delete_dangling_connections(session, cycle.id)
    return await _finish_data(session, cycle, commit=commit)


async def _unique_named(session, model, cycle_id, name, exclude_id=None):
    query = select(model).where(
        model.cycle_id == cycle_id,
        func.lower(model.name) == name.casefold(),
    )
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    return await session.scalar(query)


async def create_goal_option(
    session: AsyncSession,
    cycle: PiCycle,
    payload: PiGoalOptionDataCreate,
    *,
    commit: bool = True,
):
    name = payload.name.strip()
    if await _unique_named(session, PiCycleGoalOption, cycle.id, name):
        raise ValueError("Goal option must be unique inside a PI cycle")
    session.add(
        PiCycleGoalOption(
            cycle_id=cycle.id,
            name=name,
            sort_order=await _next_order(session, PiCycleGoalOption, cycle.id),
        )
    )
    return await _finish_data(session, cycle, commit=commit)


async def update_goal_option(
    session: AsyncSession,
    cycle: PiCycle,
    option_id: uuid.UUID,
    payload: PiGoalOptionDataUpdate,
    *,
    commit: bool = True,
):
    row = await session.scalar(
        select(PiCycleGoalOption).where(
            PiCycleGoalOption.id == option_id,
            PiCycleGoalOption.cycle_id == cycle.id,
        )
    )
    if row is None:
        raise ValueError("Goal option not found in this PI cycle")
    name = payload.name.strip()
    if await _unique_named(session, PiCycleGoalOption, cycle.id, name, row.id):
        raise ValueError("Goal option must be unique inside a PI cycle")
    row.name = name
    return await _finish_data(session, cycle, commit=commit)


async def delete_goal_option(
    session: AsyncSession,
    cycle: PiCycle,
    option_id: uuid.UUID,
    *,
    commit: bool = True,
):
    row = await session.scalar(
        select(PiCycleGoalOption).where(
            PiCycleGoalOption.id == option_id,
            PiCycleGoalOption.cycle_id == cycle.id,
        )
    )
    if row is None:
        raise ValueError("Goal option not found in this PI cycle")
    await session.delete(row)
    return await _finish_data(session, cycle, commit=commit)


async def create_tag(
    session: AsyncSession,
    cycle: PiCycle,
    payload: PiTagDataCreate,
    *,
    commit: bool = True,
):
    name = payload.name.strip()
    if await _unique_named(session, PiCycleTag, cycle.id, name):
        raise ValueError("Tag must be unique inside a PI cycle")
    session.add(
        PiCycleTag(
            cycle_id=cycle.id,
            name=name,
            sort_order=await _next_order(session, PiCycleTag, cycle.id),
        )
    )
    return await _finish_data(session, cycle, commit=commit)


async def update_tag(
    session: AsyncSession,
    cycle: PiCycle,
    tag_id: uuid.UUID,
    payload: PiTagDataUpdate,
    *,
    commit: bool = True,
):
    row = await session.scalar(
        select(PiCycleTag).where(PiCycleTag.id == tag_id, PiCycleTag.cycle_id == cycle.id)
    )
    if row is None:
        raise ValueError("Tag not found in this PI cycle")
    name = payload.name.strip()
    if await _unique_named(session, PiCycleTag, cycle.id, name, row.id):
        raise ValueError("Tag must be unique inside a PI cycle")
    old_name = row.name
    initiatives = (
        await session.scalars(select(Initiative).where(Initiative.cycle_id == cycle.id))
    ).all()
    for initiative in initiatives:
        initiative.tags = [name if value == old_name else value for value in initiative.tags or []]
    row.name = name
    return await _finish_data(session, cycle, commit=commit)


async def delete_tag(
    session: AsyncSession,
    cycle: PiCycle,
    tag_id: uuid.UUID,
    *,
    commit: bool = True,
):
    row = await session.scalar(
        select(PiCycleTag).where(PiCycleTag.id == tag_id, PiCycleTag.cycle_id == cycle.id)
    )
    if row is None:
        raise ValueError("Tag not found in this PI cycle")
    initiatives = (
        await session.scalars(select(Initiative).where(Initiative.cycle_id == cycle.id))
    ).all()
    for initiative in initiatives:
        initiative.tags = [value for value in initiative.tags or [] if value != row.name]
    await session.delete(row)
    return await _finish_data(session, cycle, commit=commit)


def _require_unique(values: list[str], label: str) -> None:
    normalized = [value.strip().casefold() for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be unique inside a PI cycle")


def _validate_snapshot_ids(items, existing, label: str) -> None:
    existing_ids = {row.id for row in existing}
    supplied_ids = [item.id for item in items if item.id is not None]
    if len(supplied_ids) != len(set(supplied_ids)):
        raise ValueError(f"Duplicate {label} id in PI data command")
    if any(item_id not in existing_ids for item_id in supplied_ids):
        raise ValueError(f"{label} does not belong to this PI cycle")


async def replace_pi_cycle_data(
    session: AsyncSession,
    cycle: PiCycle,
    payload: PiCycleDataReplace,
) -> PiCycleDataRead:
    events, teams, goals, tags = await _data_rows(session, cycle.id)
    _validate_snapshot_ids(payload.pirs, events, "PIR")
    _validate_snapshot_ids(payload.teams, teams, "cycle team")
    _validate_snapshot_ids(payload.goal_options, goals, "goal option")
    _validate_snapshot_ids(payload.tags, tags, "tag")
    _require_unique([item.name for item in payload.pirs], "PIR names")
    _require_unique(
        [f"{item.tribe.strip()}\0{item.name.strip()}" for item in payload.teams],
        "Teams",
    )
    _require_unique([item.name for item in payload.goal_options], "Goal options")
    _require_unique([item.name for item in payload.tags], "Tags")

    keep_event_ids = {item.id for item in payload.pirs if item.id is not None}
    keep_team_ids = {item.id for item in payload.teams if item.id is not None}
    keep_goal_ids = {item.id for item in payload.goal_options if item.id is not None}
    keep_tag_ids = {item.id for item in payload.tags if item.id is not None}
    command_version = payload.expected_version

    for row in events:
        if row.id not in keep_event_ids:
            await delete_pir(session, cycle, row.id, commit=False)
    for row in teams:
        if row.id not in keep_team_ids:
            await delete_cycle_team(
                session,
                cycle,
                row.id,
                PiCycleTeamDelete(
                    expected_version=command_version,
                    confirm_cascade=payload.confirm_cascade,
                ),
                commit=False,
            )
    for row in goals:
        if row.id not in keep_goal_ids:
            await delete_goal_option(session, cycle, row.id, commit=False)
    for row in tags:
        if row.id not in keep_tag_ids:
            await delete_tag(session, cycle, row.id, commit=False)

    await update_cycle_data(
        session,
        cycle,
        PiCycleDataUpdate(
            expected_version=command_version,
            start_date=payload.start_date,
            sprint_count=payload.sprint_count,
            cascade_policy=("unassign_out_of_range" if payload.confirm_cascade else None),
        ),
        commit=False,
        validate_events=False,
    )

    for item in payload.pirs:
        command = PiEventDataUpdate(
            expected_version=command_version,
            name=item.name,
            date=item.date,
        )
        if item.id is None:
            await create_pir(session, cycle, command, commit=False)
        else:
            await update_pir(session, cycle, item.id, command, commit=False)

    for item in payload.teams:
        command = PiCycleTeamDataUpdate(
            expected_version=command_version,
            tribe=item.tribe,
            name=item.name,
            team_type=item.team_type,
            excluded_from_goals=item.excluded_from_goals,
            competencies=item.competencies,
            cascade_policy=("remove_competency_usage" if payload.confirm_cascade else None),
        )
        if item.id is None:
            await create_cycle_team(session, cycle, command, commit=False)
        else:
            await update_cycle_team(session, cycle, item.id, command, commit=False)

    for item in payload.goal_options:
        command = PiGoalOptionDataUpdate(
            expected_version=command_version,
            name=item.name,
        )
        if item.id is None:
            await create_goal_option(session, cycle, command, commit=False)
        else:
            await update_goal_option(session, cycle, item.id, command, commit=False)

    for item in payload.tags:
        command = PiTagDataUpdate(expected_version=command_version, name=item.name)
        if item.id is None:
            await create_tag(session, cycle, command, commit=False)
        else:
            await update_tag(session, cycle, item.id, command, commit=False)

    await session.flush()
    final_events, final_teams, final_goals, final_tags = await _data_rows(session, cycle.id)
    event_by_id = {row.id: row for row in final_events}
    team_by_id = {row.id: row for row in final_teams}
    goal_by_id = {row.id: row for row in final_goals}
    tag_by_id = {row.id: row for row in final_tags}
    event_by_name = {row.name.casefold(): row for row in final_events}
    team_by_name = {
        (row.team.tribe.name.casefold(), row.team.name.casefold()): row
        for row in final_teams
    }
    goal_by_name = {row.name.casefold(): row for row in final_goals}
    tag_by_name = {row.name.casefold(): row for row in final_tags}
    for index, item in enumerate(payload.pirs):
        (event_by_id[item.id] if item.id else event_by_name[item.name.strip().casefold()]).sort_order = index
    for index, item in enumerate(payload.teams):
        (
            team_by_id[item.id]
            if item.id
            else team_by_name[(item.tribe.strip().casefold(), item.name.strip().casefold())]
        ).sort_order = index
    for index, item in enumerate(payload.goal_options):
        (goal_by_id[item.id] if item.id else goal_by_name[item.name.strip().casefold()]).sort_order = index
    for index, item in enumerate(payload.tags):
        (tag_by_id[item.id] if item.id else tag_by_name[item.name.strip().casefold()]).sort_order = index
    return await _commit_data(session, cycle)
