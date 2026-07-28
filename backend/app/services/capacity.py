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
)
from app.schemas.pi_cycle import (
    CapacityMemberRead,
    CapacityRead,
    CapacitySprintRead,
    CapacityTeamRead,
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


def calculate_member_capacity(
    member: PiCycleCapacityMember,
    cycle: PiCycle,
) -> tuple[float, float, list[CapacitySprintRead]]:
    calendar_capacity = 0.0
    available_capacity = 0.0
    sprint_rows: list[CapacitySprintRead] = []
    for sprint in compute_sprints(cycle):
        workdays = workdays_between(sprint.start_date, sprint.end_date)
        planned = workdays * member.rate
        vacation_days = _workdays_in_ranges(
            member.vacation_ranges,
            sprint.start_date,
            sprint.end_date,
        )
        extra_days = _workdays_in_ranges(
            member.extra_unavailable_ranges,
            sprint.start_date,
            sprint.end_date,
        )
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
    return calendar_capacity, available_capacity, sprint_rows


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


async def read_capacity(session: AsyncSession, cycle: PiCycle) -> CapacityRead:
    cycle_teams = await _cycle_teams(session, cycle.id)
    members = await _members(session, cycle.id)
    members_by_team: dict[uuid.UUID, list[PiCycleCapacityMember]] = {}
    for member in members:
        members_by_team.setdefault(member.team_id, []).append(member)
    planned_by_team = await _planned_by_team(session, cycle.id)

    rows: list[CapacityTeamRead] = []
    for cycle_team in cycle_teams:
        team_members: list[CapacityMemberRead] = []
        available_by_competency: dict[str, float] = {
            row.code: 0.0 for row in cycle_team.competencies
        }
        calendar_capacity = 0.0
        available_capacity = 0.0
        for member in members_by_team.get(cycle_team.team_id, []):
            calendar, available, sprint_rows = calculate_member_capacity(member, cycle)
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
                )
            )
        planned = planned_by_team.get(cycle_team.team_id, {})
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
