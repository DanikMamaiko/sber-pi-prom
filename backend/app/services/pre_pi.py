import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    Initiative,
    InitiativeExecutor,
    PiCycle,
    PiGoal,
    Team,
)
from app.schemas.pi_cycle import (
    PrePiInitiativeRead,
    PrePiRead,
    PrePiWrite,
)
from app.services.program_board import delete_dangling_connections
from app.services.validation import (
    cycle_team_context,
    normalized_effort,
    resolve_cycle_team,
    validate_sprint_position,
)


def _clean_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = raw.strip()
        if value and value not in result:
            result.append(value)
    return result


async def _initiatives_query(session: AsyncSession, cycle_id: uuid.UUID) -> list[Initiative]:
    return list(
        (
            await session.scalars(
                select(Initiative)
                .options(
                    selectinload(Initiative.owner_team).selectinload(Team.tribe),
                    selectinload(Initiative.executors)
                    .selectinload(InitiativeExecutor.team)
                    .selectinload(Team.tribe),
                )
                .where(Initiative.cycle_id == cycle_id)
                .order_by(Initiative.sort_order, Initiative.created_at, Initiative.id)
            )
        ).all()
    )


async def read_pre_pi(session: AsyncSession, cycle: PiCycle) -> PrePiRead:
    initiatives = await _initiatives_query(session, cycle.id)
    rows: list[PrePiInitiativeRead] = []
    for item in initiatives:
        rows.append(
            PrePiInitiativeRead(
                id=item.id,
                issue_key=item.issue_key,
                title=item.title,
                description=item.description or "",
                product=item.product or "",
                owner_team=item.owner_team.name if item.owner_team else "",
                owner_tribe=(
                    item.owner_team.tribe.name
                    if item.owner_team and item.owner_team.tribe
                    else ""
                ),
                initiative_type=item.initiative_type or "",
                status=item.status or "backlog",
                goal_text=item.goal_text or "",
                metric=item.metric or "",
                current_value=item.current_value or "",
                target_value=item.target_value or "",
                hypothesis=item.hypothesis or "",
                redesign=item.redesign or "",
                customer_priority=item.customer_priority or "",
                team_priority=item.team_priority or "",
                estimate=item.estimate or "",
                comment=item.comment or "",
                pre_planned=bool(item.pre_planned),
                on_board=bool(item.on_board),
                agreed=bool(item.agreed),
                tags=list(item.tags or []),
                sprint_index=item.sprint_index,
                week_index=item.week_index,
                sort_order=item.sort_order,
                executors=[
                    {
                        "team": executor.team.name,
                        "tribe": executor.team.tribe.name if executor.team.tribe else "",
                        "effort_by_competency": dict(executor.effort_by_competency or {}),
                        "attractions": list(executor.attractions or []),
                        "sort_order": executor.sort_order,
                    }
                    for executor in sorted(item.executors, key=lambda row: row.sort_order)
                ],
            )
        )
    return PrePiRead(
        initialized=cycle.initiatives_initialized,
        version=cycle.version,
        initiatives=rows,
    )


async def replace_pre_pi(
    session: AsyncSession,
    cycle: PiCycle,
    payload: PrePiWrite,
) -> PrePiRead:
    normalized_keys = [row.issue_key.strip().casefold() for row in payload.initiatives]
    if len(normalized_keys) != len(set(normalized_keys)):
        raise ValueError("Issue ID must be unique inside a PI cycle")

    teams_by_key, teams_by_name, competencies_by_team = await cycle_team_context(
        session, cycle.id
    )
    payload_issue_keys = set(normalized_keys)

    existing = await _initiatives_query(session, cycle.id)
    by_id = {row.id: row for row in existing}
    by_key = {row.issue_key.casefold(): row for row in existing}
    used_ids: set[uuid.UUID] = set()

    for position, source in enumerate(payload.initiatives):
        issue_key = source.issue_key.strip()
        item = by_id.get(source.id) if source.id else None
        key_match = by_key.get(issue_key.casefold())
        if source.id is not None and item is None:
            raise ValueError(f"Initiative ID is not found in this PI cycle: {source.id}")
        if item is not None and key_match is not None and item.id != key_match.id:
            raise ValueError(f"Issue ID already exists in this PI cycle: {issue_key}")
        if item is None:
            item = key_match
        if item is not None and item.id in used_ids:
            raise ValueError(f"Initiative is included more than once: {issue_key}")
        if item is None:
            item = Initiative(
                id=uuid.uuid4(),
                cycle_id=cycle.id,
                issue_key=issue_key,
                title=source.title.strip(),
                executors=[],
            )
            session.add(item)
        used_ids.add(item.id)

        validate_sprint_position(
            cycle,
            source.sprint_index,
            source.week_index,
            f"Initiative {issue_key}",
        )
        owner = None
        if source.owner_team.strip():
            owner = resolve_cycle_team(
                teams_by_key,
                teams_by_name,
                source.owner_tribe,
                source.owner_team,
            )
        item.issue_key = issue_key
        item.title = source.title.strip()
        item.description = source.description
        item.product = source.product.strip()
        item.owner_team_id = owner.id if owner else None
        item.initiative_type = source.initiative_type.strip()
        item.status = source.status.strip() or "backlog"
        item.goal_text = source.goal_text.strip()
        item.metric = source.metric.strip()
        item.current_value = source.current_value.strip()
        item.target_value = source.target_value.strip()
        item.hypothesis = source.hypothesis
        item.redesign = source.redesign
        item.customer_priority = source.customer_priority.strip()
        item.team_priority = source.team_priority.strip()
        item.estimate = source.estimate.strip()
        item.comment = source.comment
        item.pre_planned = source.pre_planned
        item.on_board = source.on_board
        item.agreed = source.agreed
        item.tags = _clean_unique(source.tags)
        item.sprint_index = source.sprint_index
        item.week_index = source.week_index
        item.sort_order = source.sort_order if source.sort_order is not None else position

        existing_executors = {executor.team_id: executor for executor in item.executors}
        executors: list[InitiativeExecutor] = []
        executor_team_ids: set[uuid.UUID] = set()
        for executor_position, source_executor in enumerate(source.executors):
            team = resolve_cycle_team(
                teams_by_key,
                teams_by_name,
                source_executor.tribe,
                source_executor.team,
            )
            if team.id in executor_team_ids:
                raise ValueError(
                    f"Executor team is included more than once for {issue_key}: {team.name}"
                )
            executor_team_ids.add(team.id)
            record = existing_executors.get(team.id)
            if record is None:
                record = InitiativeExecutor(team_id=team.id)
            record.effort_by_competency = normalized_effort(
                source_executor.effort_by_competency,
                competencies_by_team.get(team.id, set()),
                f"Pre PI {issue_key} / {team.name}",
            )
            attractions = []
            for attraction in source_executor.attractions:
                validate_sprint_position(
                    cycle,
                    attraction.sprint_index,
                    None,
                    f"Attraction {attraction.issue_key}",
                )
                if attraction.issue_key.strip().casefold() not in payload_issue_keys:
                    raise ValueError(
                        f"Attraction initiative is not found in this PI cycle: "
                        f"{attraction.issue_key}"
                    )
                if attraction.team.strip():
                    resolve_cycle_team(
                        teams_by_key,
                        teams_by_name,
                        "",
                        attraction.team,
                    )
                attractions.append(attraction.model_dump())
            record.attractions = attractions
            record.sort_order = source_executor.sort_order or executor_position
            executors.append(record)
        item.executors = executors

    removed_ids = [row.id for row in existing if row.id not in used_ids]
    if removed_ids:
        await session.execute(
            update(PiGoal)
            .where(PiGoal.initiative_id.in_(removed_ids))
            .values(initiative_id=None)
        )
        for item in existing:
            if item.id in removed_ids:
                await session.delete(item)

    cycle.initiatives_initialized = True
    await delete_dangling_connections(session, cycle.id)
    await session.commit()
    return await read_pre_pi(session, cycle)
