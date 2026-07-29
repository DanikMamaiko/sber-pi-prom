import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    Initiative,
    InitiativeExecutor,
    PiCycle,
    PiCycleCapacityMember,
    PiCycleTeam,
    Team,
    WorkItem,
)
from app.schemas.pi_cycle import (
    CapacityMemberRead,
    CapacityMemberCreate,
    CapacityMemberUpdate,
    CapacityRead,
    CapacitySprintRead,
    CapacityTeamRead,
    CapacityWeekRead,
    CapacityWrite,
)
from app.services.planning import compute_sprints, workdays_between


def _range_dates(value: dict) -> tuple[date, date]:
    start = date.fromisoformat(str(value["start"]))
    end = date.fromisoformat(str(value["end"]))
    if end < start:
        raise ValueError("Unavailable range end cannot be earlier than start")
    return start, end


def _workdays_in_ranges(values: list[dict], start: date, end: date) -> int:
    days: set[date] = set()
    for value in values or []:
        range_start, range_end = _range_dates(value)
        cursor = max(start, range_start)
        overlap_end = min(end, range_end)
        while cursor <= overlap_end:
            if cursor.weekday() < 5:
                days.add(cursor)
            cursor += timedelta(days=1)
    return len(days)


def _period_capacity(
    member: PiCycleCapacityMember,
    start: date,
    end: date,
) -> tuple[int, float, int, int, float]:
    workdays = workdays_between(start, end)
    planned = workdays * member.rate
    vacation_days = _workdays_in_ranges(member.vacation_ranges, start, end)
    extra_days = _workdays_in_ranges(member.extra_unavailable_ranges, start, end)
    available = max(
        0.0,
        planned
        - vacation_days * member.rate
        - extra_days * member.rate
        - planned * member.ceremony_percent / 100
        - planned * member.risk_percent / 100,
    )
    if member.efficiency is not None:
        available *= member.efficiency
    return workdays, planned, vacation_days, extra_days, available


def calculate_member_capacity_with_weeks(
    member: PiCycleCapacityMember,
    cycle: PiCycle,
) -> tuple[
    float,
    float,
    list[CapacitySprintRead],
    dict[int, list[CapacityWeekRead]],
]:
    calendar_capacity = 0.0
    available_capacity = 0.0
    sprint_rows: list[CapacitySprintRead] = []
    week_rows: dict[int, list[CapacityWeekRead]] = {}
    for sprint in compute_sprints(cycle):
        workdays, planned, vacation_days, extra_days, available = _period_capacity(
            member, sprint.start_date, sprint.end_date
        )
        calendar_capacity += planned
        available_capacity += available
        sprint_rows.append(
            CapacitySprintRead(
                sprint_index=sprint.index,
                workdays=workdays,
                planned_capacity=planned,
                vacation_days=vacation_days,
                extra_unavailable_days=extra_days,
                available_capacity=available,
            )
        )
        week_rows[sprint.index] = []
        for week_index in (0, 1):
            week_start = sprint.start_date + timedelta(days=week_index * 7)
            week_end = min(week_start + timedelta(days=6), sprint.end_date)
            week_values = _period_capacity(member, week_start, week_end)
            week_rows[sprint.index].append(
                CapacityWeekRead(
                    week_index=week_index,
                    workdays=week_values[0],
                    planned_capacity=week_values[1],
                    vacation_days=week_values[2],
                    extra_unavailable_days=week_values[3],
                    available_capacity=week_values[4],
                )
            )
    return calendar_capacity, available_capacity, sprint_rows, week_rows


def calculate_member_capacity(
    member: PiCycleCapacityMember,
    cycle: PiCycle,
) -> tuple[float, float, list[CapacitySprintRead]]:
    calendar, available, sprints, _ = calculate_member_capacity_with_weeks(member, cycle)
    return calendar, available, sprints


async def _cycle_teams(session: AsyncSession, cycle_id: uuid.UUID) -> list[PiCycleTeam]:
    return list(
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


async def _members(
    session: AsyncSession,
    cycle_id: uuid.UUID,
) -> list[PiCycleCapacityMember]:
    return list(
        (
            await session.scalars(
                select(PiCycleCapacityMember)
                .where(PiCycleCapacityMember.cycle_id == cycle_id)
                .order_by(
                    PiCycleCapacityMember.team_id,
                    PiCycleCapacityMember.sort_order,
                    PiCycleCapacityMember.created_at,
                    PiCycleCapacityMember.id,
                )
            )
        ).all()
    )


async def _planned_by_team(
    session: AsyncSession,
    cycle_id: uuid.UUID,
) -> dict[uuid.UUID, dict[str, float]]:
    result: dict[uuid.UUID, dict[str, float]] = {}
    executors = (
        await session.scalars(
            select(InitiativeExecutor)
            .join(Initiative, Initiative.id == InitiativeExecutor.initiative_id)
            .where(
                Initiative.cycle_id == cycle_id,
                Initiative.pre_planned.is_(True),
            )
        )
    ).all()
    for executor in executors:
        target = result.setdefault(executor.team_id, {})
        for competency, effort in (executor.effort_by_competency or {}).items():
            code = str(competency).strip().upper()
            if code:
                target[code] = target.get(code, 0.0) + float(effort or 0)
    return result


async def _board_load_by_team(
    session: AsyncSession,
    cycle_id: uuid.UUID,
) -> dict[uuid.UUID, dict[str, object]]:
    result: dict[uuid.UUID, dict[str, object]] = {}
    initiatives = list(
        (
            await session.scalars(
                select(Initiative)
                .options(
                    selectinload(Initiative.executors),
                    selectinload(Initiative.work_items),
                )
                .where(Initiative.cycle_id == cycle_id, Initiative.on_board.is_(True))
            )
        ).all()
    )
    for initiative in initiatives:
        executors = sorted(
            initiative.executors,
            key=lambda row: (row.sort_order, str(row.id)),
        )
        if not executors:
            continue
        team_id = executors[0].team_id
        target = result.setdefault(
            team_id,
            {"total": {}, "sprints": {}, "weeks": {}},
        )

        def add(competency: str, effort: float, sprint_index: int, week_index: int) -> None:
            code = competency.strip().upper()
            value = float(effort or 0)
            target["total"][code] = target["total"].get(code, 0.0) + value
            sprint = target["sprints"].setdefault(sprint_index, {})
            sprint[code] = sprint.get(code, 0.0) + value
            week = target["weeks"].setdefault(sprint_index, {}).setdefault(week_index, {})
            week[code] = week.get(code, 0.0) + value

        if initiative.work_items:
            for item in initiative.work_items:
                if item.sprint_index is not None:
                    add(item.competency, item.effort, item.sprint_index, item.week_index or 0)
        elif initiative.sprint_index is not None:
            for competency, effort in (executors[0].effort_by_competency or {}).items():
                add(
                    str(competency),
                    float(effort or 0),
                    initiative.sprint_index,
                    initiative.week_index or 0,
                )
    return result


async def read_capacity(session: AsyncSession, cycle: PiCycle) -> CapacityRead:
    cycle_teams = await _cycle_teams(session, cycle.id)
    members = await _members(session, cycle.id)
    members_by_team: dict[uuid.UUID, list[PiCycleCapacityMember]] = {}
    for member in members:
        members_by_team.setdefault(member.team_id, []).append(member)
    planned_by_team = await _planned_by_team(session, cycle.id)
    board_load_by_team = await _board_load_by_team(session, cycle.id)

    rows: list[CapacityTeamRead] = []
    for cycle_team in cycle_teams:
        team_members: list[CapacityMemberRead] = []
        available_by_competency: dict[str, float] = {
            row.code: 0.0 for row in cycle_team.competencies
        }
        calendar_capacity = 0.0
        available_capacity = 0.0
        for member in members_by_team.get(cycle_team.team_id, []):
            calendar, available, sprint_rows, week_rows = calculate_member_capacity_with_weeks(
                member, cycle
            )
            calendar_capacity += calendar
            available_capacity += available
            available_by_competency[member.competency] = (
                available_by_competency.get(member.competency, 0.0) + available
            )
            team_members.append(
                CapacityMemberRead(
                    id=member.id,
                    client_uid=member.client_uid,
                    full_name=member.full_name,
                    competency=member.competency,
                    rate=member.rate,
                    vacation_ranges=member.vacation_ranges,
                    extra_unavailable_ranges=member.extra_unavailable_ranges,
                    ceremony_percent=member.ceremony_percent,
                    risk_percent=member.risk_percent,
                    efficiency=member.efficiency,
                    sort_order=member.sort_order,
                    calendar_capacity=calendar,
                    available_capacity=available,
                    sprints=sprint_rows,
                    weeks=week_rows,
                )
            )
        planned = planned_by_team.get(cycle_team.team_id, {})
        board_load = board_load_by_team.get(
            cycle_team.team_id, {"total": {}, "sprints": {}, "weeks": {}}
        )
        rows.append(
            CapacityTeamRead(
                tribe=cycle_team.team.tribe.name,
                team=cycle_team.team.name,
                members=team_members,
                calendar_capacity=calendar_capacity,
                available_capacity=available_capacity,
                planned_effort=sum(planned.values()),
                available_by_competency=available_by_competency,
                planned_by_competency=planned,
                load_by_competency=board_load["total"],
                load_by_sprint=board_load["sprints"],
                load_by_week=board_load["weeks"],
            )
        )
    return CapacityRead(initialized=cycle.capacity_initialized, version=cycle.version, teams=rows)


async def replace_capacity(
    session: AsyncSession,
    cycle: PiCycle,
    payload: CapacityWrite,
) -> CapacityRead:
    team_keys = [
        (row.tribe.strip().casefold(), row.team.strip().casefold())
        for row in payload.teams
    ]
    if len(team_keys) != len(set(team_keys)):
        raise ValueError("A team can only occur once in the capacity payload")
    member_uids = [
        member.client_uid.strip().casefold()
        for team in payload.teams
        for member in team.members
    ]
    if len(member_uids) != len(set(member_uids)):
        raise ValueError("Capacity member UID must be unique inside a PI cycle")

    cycle_teams = await _cycle_teams(session, cycle.id)
    teams_by_key = {
        (row.team.tribe.name.casefold(), row.team.name.casefold()): row.team
        for row in cycle_teams
    }
    competencies_by_team = {
        row.team_id: {item.code.strip().upper() for item in row.competencies}
        for row in cycle_teams
    }
    existing = await _members(session, cycle.id)
    existing_by_id = {row.id: row for row in existing}
    existing_by_uid = {row.client_uid.casefold(): row for row in existing}
    desired_ids: set[uuid.UUID] = set()

    for source_team in payload.teams:
        key = (source_team.tribe.strip().casefold(), source_team.team.strip().casefold())
        team = teams_by_key.get(key)
        if team is None:
            raise ValueError(
                f"Team is not included in this PI cycle: {source_team.tribe} / {source_team.team}"
            )
        for position, source in enumerate(source_team.members):
            uid = source.client_uid.strip()
            member = existing_by_id.get(source.id) if source.id else None
            uid_match = existing_by_uid.get(uid.casefold())
            if source.id is not None and member is None:
                raise ValueError(
                    f"Capacity member ID is not found in this PI cycle: {source.id}"
                )
            if member is not None and uid_match is not None and member.id != uid_match.id:
                raise ValueError(f"Capacity member ID does not match client UID: {uid}")
            if member is None:
                member = uid_match
            if member is None:
                member = PiCycleCapacityMember(
                    id=uuid.uuid4(),
                    cycle_id=cycle.id,
                    team_id=team.id,
                    client_uid=uid,
                    competency=source.competency.strip().upper(),
                )
                session.add(member)
            vacation_ranges = [row.model_dump(mode="json") for row in source.vacation_ranges]
            extra_ranges = [
                row.model_dump(mode="json") for row in source.extra_unavailable_ranges
            ]
            for value in vacation_ranges + extra_ranges:
                _range_dates(value)
            competency = source.competency.strip().upper()
            if competency not in competencies_by_team.get(team.id, set()):
                raise ValueError(
                    f"Capacity member {uid}: competency is not configured for team "
                    f"{team.name}: {competency}"
                )
            member.team_id = team.id
            member.client_uid = uid
            member.full_name = source.full_name.strip()
            member.competency = competency
            member.rate = float(source.rate)
            member.vacation_ranges = vacation_ranges
            member.extra_unavailable_ranges = extra_ranges
            member.ceremony_percent = float(source.ceremony_percent)
            member.risk_percent = float(source.risk_percent)
            member.efficiency = (
                float(source.efficiency) if source.efficiency is not None else None
            )
            member.sort_order = source.sort_order if source.sort_order is not None else position
            desired_ids.add(member.id)

    for member in existing:
        if member.id not in desired_ids:
            await session.delete(member)
    cycle.capacity_initialized = True
    await session.commit()
    return await read_capacity(session, cycle)


async def _capacity_team_by_name(
    session: AsyncSession,
    cycle: PiCycle,
    tribe: str,
    team: str,
) -> PiCycleTeam:
    key = (tribe.strip().casefold(), team.strip().casefold())
    cycle_team = next(
        (
            row
            for row in await _cycle_teams(session, cycle.id)
            if (row.team.tribe.name.casefold(), row.team.name.casefold()) == key
        ),
        None,
    )
    if cycle_team is None:
        raise ValueError(f"Team is not included in this PI cycle: {tribe} / {team}")
    return cycle_team


def _capacity_values(payload, *, exclude: set[str] | None = None) -> dict:
    data = payload.model_dump(exclude_unset=True, exclude=exclude or set())
    for field in ("vacation_ranges", "extra_unavailable_ranges"):
        if field in data:
            data[field] = [
                row.model_dump(mode="json") if hasattr(row, "model_dump") else row
                for row in (getattr(payload, field) or [])
            ]
            for value in data[field]:
                _range_dates(value)
    return data


async def create_capacity_member(
    session: AsyncSession,
    cycle: PiCycle,
    payload: CapacityMemberCreate,
) -> CapacityRead:
    cycle_team = await _capacity_team_by_name(
        session, cycle, payload.tribe, payload.team
    )
    uid = payload.client_uid.strip()
    if await session.scalar(
        select(PiCycleCapacityMember.id).where(
            PiCycleCapacityMember.cycle_id == cycle.id,
            PiCycleCapacityMember.client_uid.ilike(uid),
        )
    ):
        raise ValueError(f"Capacity member UID must be unique inside a PI cycle: {uid}")
    competency = payload.competency.strip().upper()
    allowed = {row.code.strip().upper() for row in cycle_team.competencies}
    if competency not in allowed:
        raise ValueError(
            f"Capacity member {uid}: competency is not configured for team "
            f"{cycle_team.team.name}: {competency}"
        )
    values = _capacity_values(
        payload,
        exclude={"expected_version", "id", "tribe", "team", "client_uid", "competency"},
    )
    member = PiCycleCapacityMember(
        id=uuid.uuid4(),
        cycle_id=cycle.id,
        team_id=cycle_team.team_id,
        client_uid=uid,
        competency=competency,
        **values,
    )
    session.add(member)
    cycle.capacity_initialized = True
    await session.commit()
    return await read_capacity(session, cycle)


async def update_capacity_member(
    session: AsyncSession,
    cycle: PiCycle,
    member_id: uuid.UUID,
    payload: CapacityMemberUpdate,
) -> CapacityRead:
    member = await session.scalar(
        select(PiCycleCapacityMember).where(
            PiCycleCapacityMember.cycle_id == cycle.id,
            PiCycleCapacityMember.id == member_id,
        )
    )
    if member is None:
        raise ValueError("Capacity member is not found in this PI cycle")
    cycle_team = next(
        (row for row in await _cycle_teams(session, cycle.id) if row.team_id == member.team_id),
        None,
    )
    if cycle_team is None:
        raise ValueError("Capacity member team is not included in this PI cycle")
    values = _capacity_values(payload, exclude={"expected_version"})
    if "competency" in values:
        competency = str(values["competency"]).strip().upper()
        allowed = {row.code.strip().upper() for row in cycle_team.competencies}
        if competency not in allowed:
            raise ValueError(
                f"Capacity member {member.client_uid}: competency is not configured for team "
                f"{cycle_team.team.name}: {competency}"
            )
        values["competency"] = competency
    for field, value in values.items():
        setattr(member, field, value.strip() if field == "full_name" else value)
    await session.commit()
    return await read_capacity(session, cycle)


async def delete_capacity_member(
    session: AsyncSession,
    cycle: PiCycle,
    member_id: uuid.UUID,
    *,
    confirm_cascade: bool = False,
) -> CapacityRead:
    member = await session.scalar(
        select(PiCycleCapacityMember).where(
            PiCycleCapacityMember.cycle_id == cycle.id,
            PiCycleCapacityMember.id == member_id,
        )
    )
    if member is None:
        raise ValueError("Capacity member is not found in this PI cycle")
    assigned = list(
        (
            await session.scalars(
                select(WorkItem)
                .join(Initiative, Initiative.id == WorkItem.initiative_id)
                .where(
                    Initiative.cycle_id == cycle.id,
                    WorkItem.assignee_member_id == member.id,
                )
            )
        ).all()
    )
    if assigned and not confirm_cascade:
        from app.services.team_boards import TeamBoardCascadeRequired

        raise TeamBoardCascadeRequired(
            "Deleting the capacity member clears assignments on work items",
            [
                {"kind": "work_item", "id": str(row.id), "label": row.client_uid}
                for row in assigned
            ],
        )
    for item in assigned:
        item.assignee_member_id = None
        item.assignee_name = ""
    await session.delete(member)
    await session.commit()
    return await read_capacity(session, cycle)
