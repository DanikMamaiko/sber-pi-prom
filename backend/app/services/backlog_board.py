import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    BacklogBoardState,
    BacklogExecutor,
    BacklogItem,
    Initiative,
    InitiativeExecutor,
    PiCycle,
    Team,
    Tribe,
)
from app.schemas.pi_cycle import (
    BacklogBoardItemRead,
    BacklogBoardRead,
    BacklogBoardWrite,
    BacklogDispatchRead,
    BacklogDispatchWrite,
    InitiativeRead,
)
from app.services.validation import cycle_team_context, normalized_effort


BACKLOG_STATE_ID = 1
SENT_STATUS = "Отправлена в Pre PI Planning"


def _clean_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = raw.strip()
        if value and value not in result:
            result.append(value)
    return result


async def _items_query(session: AsyncSession) -> list[BacklogItem]:
    return list(
        (
            await session.scalars(
                select(BacklogItem)
                .options(
                    selectinload(BacklogItem.tribe),
                    selectinload(BacklogItem.owner_team).selectinload(Team.tribe),
                    selectinload(BacklogItem.executors)
                    .selectinload(BacklogExecutor.team)
                    .selectinload(Team.tribe),
                )
                .order_by(BacklogItem.sort_order, BacklogItem.created_at, BacklogItem.id)
            )
        ).all()
    )


async def read_backlog_board(session: AsyncSession) -> BacklogBoardRead:
    marker = await session.get(BacklogBoardState, BACKLOG_STATE_ID)
    items = await _items_query(session)
    rows: list[BacklogBoardItemRead] = []
    for item in items:
        tribe_name = item.tribe.name if item.tribe else ""
        if not tribe_name and item.owner_team and item.owner_team.tribe:
            tribe_name = item.owner_team.tribe.name
        if not tribe_name:
            # Legacy rows without a tribe remain accessible and can be repaired
            # through the aggregate PUT instead of making the whole board fail.
            tribe_name = "Без трайба"
        rows.append(
            BacklogBoardItemRead(
                id=item.id,
                tribe=tribe_name,
                issue_key=item.issue_key,
                title=item.title,
                description=item.description or "",
                product=item.product or "",
                owner_team=item.owner_team.name if item.owner_team else "",
                initiative_type=item.initiative_type or "",
                target_year=item.target_year,
                target_quarter=item.target_quarter,
                customer_priority=item.customer_priority or "",
                team_priority=item.team_priority or "",
                status=item.status or "Нет оценки",
                systems=list(item.systems or []),
                sent_to=list(item.sent_to or []),
                sort_order=item.sort_order,
                executors=[
                    {
                        "team": executor.team.name,
                        "effort_by_competency": dict(executor.effort_by_competency or {}),
                    }
                    for executor in item.executors
                ],
            )
        )
    return BacklogBoardRead(
        initialized=bool(marker and marker.initialized),
        version=marker.version if marker else 0,
        items=rows,
    )


async def _resolve_tribe(
    session: AsyncSession,
    name: str,
    cache: dict[str, Tribe],
) -> Tribe:
    value = name.strip()
    if value in cache:
        return cache[value]
    tribe = await session.scalar(select(Tribe).where(Tribe.name == value))
    if tribe is None:
        tribe = Tribe(name=value)
        session.add(tribe)
        await session.flush()
    cache[value] = tribe
    return tribe


async def _resolve_team(
    session: AsyncSession,
    name: str,
    preferred_tribe: Tribe,
    cache: dict[tuple[str, uuid.UUID], Team],
) -> Team | None:
    value = name.strip()
    if not value:
        return None
    key = (value, preferred_tribe.id)
    if key in cache:
        return cache[key]
    teams = list((await session.scalars(select(Team).where(Team.name == value))).all())
    preferred = next((team for team in teams if team.tribe_id == preferred_tribe.id), None)
    if preferred:
        cache[key] = preferred
        return preferred
    if len(teams) == 1:
        cache[key] = teams[0]
        return teams[0]
    if len(teams) > 1:
        raise ValueError(f"Team name is ambiguous across tribes: {value}")
    team = Team(tribe_id=preferred_tribe.id, name=value)
    session.add(team)
    await session.flush()
    cache[key] = team
    return team


async def replace_backlog_board(
    session: AsyncSession,
    payload: BacklogBoardWrite,
) -> BacklogBoardRead:
    normalized_keys = [item.issue_key.strip().casefold() for item in payload.items]
    if len(normalized_keys) != len(set(normalized_keys)):
        raise ValueError("Issue ID must be unique across the global backlog")

    existing = await _items_query(session)
    by_id = {item.id: item for item in existing}
    by_key = {item.issue_key.casefold(): item for item in existing}
    used_ids: set[uuid.UUID] = set()
    tribe_cache: dict[str, Tribe] = {}
    team_cache: dict[tuple[str, uuid.UUID], Team] = {}

    for position, source in enumerate(payload.items):
        issue_key = source.issue_key.strip()
        item = by_id.get(source.id) if source.id else None
        key_match = by_key.get(issue_key.casefold())
        if source.id is not None and item is None:
            raise ValueError(f"Backlog item ID is not found: {source.id}")
        if item is not None and key_match is not None and item.id != key_match.id:
            raise ValueError(f"Issue ID already exists in the global backlog: {issue_key}")
        if item is None:
            item = key_match
        if item is not None and item.id in used_ids:
            raise ValueError(f"Backlog item is included more than once: {issue_key}")
        if item is None:
            item = BacklogItem(
                id=uuid.uuid4(),
                issue_key=issue_key,
                title=source.title.strip(),
                executors=[],
            )
            session.add(item)
        used_ids.add(item.id)

        tribe = await _resolve_tribe(session, source.tribe, tribe_cache)
        owner = await _resolve_team(session, source.owner_team, tribe, team_cache)
        item.tribe_id = tribe.id
        item.issue_key = issue_key
        item.title = source.title.strip()
        item.description = source.description
        item.product = source.product.strip()
        item.owner_team_id = owner.id if owner else None
        item.initiative_type = source.initiative_type.strip()
        item.target_year = source.target_year
        item.target_quarter = source.target_quarter
        item.customer_priority = source.customer_priority.strip()
        item.team_priority = source.team_priority.strip()
        item.status = source.status.strip() or "Нет оценки"
        item.systems = _clean_unique(source.systems)
        item.sent_to = _clean_unique(source.sent_to)
        item.sort_order = source.sort_order if source.sort_order is not None else position

        existing_executors = {executor.team_id: executor for executor in item.executors}
        executors: list[BacklogExecutor] = []
        executor_team_ids: set[uuid.UUID] = set()
        for executor in source.executors:
            team = await _resolve_team(session, executor.team, tribe, team_cache)
            if team is None:
                continue
            if team.id in executor_team_ids:
                raise ValueError(
                    f"Executor team is included more than once for {issue_key}: {team.name}"
                )
            executor_team_ids.add(team.id)
            record = existing_executors.get(team.id)
            if record is None:
                record = BacklogExecutor(team_id=team.id)
            record.effort_by_competency = normalized_effort(
                executor.effort_by_competency,
                None,
                f"Backlog {issue_key} / {team.name}",
            )
            executors.append(record)
        item.executors = executors

    removed_ids = [item.id for item in existing if item.id not in used_ids]
    if removed_ids:
        # A dispatched PI initiative is an independent planning copy. Removing
        # its source row must not remove or invalidate that PI-cycle record.
        await session.execute(
            update(Initiative)
            .where(Initiative.backlog_item_id.in_(removed_ids))
            .values(backlog_item_id=None)
        )
        for item in existing:
            if item.id in removed_ids:
                await session.delete(item)

    marker = await session.get(BacklogBoardState, BACKLOG_STATE_ID)
    if marker is None:
        marker = BacklogBoardState(id=BACKLOG_STATE_ID, initialized=True)
        session.add(marker)
    else:
        marker.initialized = True
    await session.commit()
    return await read_backlog_board(session)


async def dispatch_backlog_items(
    session: AsyncSession,
    cycle: PiCycle,
    payload: BacklogDispatchWrite,
) -> BacklogDispatchRead:
    requested_ids = list(dict.fromkeys(payload.backlog_item_ids))
    items = list(
        (
            await session.scalars(
                select(BacklogItem)
                .options(selectinload(BacklogItem.executors))
                .where(BacklogItem.id.in_(requested_ids))
            )
        ).all()
    )
    by_id = {item.id: item for item in items}
    missing = [str(item_id) for item_id in requested_ids if item_id not in by_id]
    if missing:
        raise ValueError(f"Backlog items not found: {', '.join(missing)}")

    _, _, competencies_by_team = await cycle_team_context(session, cycle.id)
    for source in items:
        if source.owner_team_id is not None and source.owner_team_id not in competencies_by_team:
            raise ValueError(
                f"Owner team is not part of this PI cycle for {source.issue_key}"
            )
        for executor in source.executors:
            if executor.team_id not in competencies_by_team:
                raise ValueError(
                    f"Executor team is not part of this PI cycle for {source.issue_key}"
                )
            executor.effort_by_competency = normalized_effort(
                executor.effort_by_competency or {},
                competencies_by_team[executor.team_id],
                f"Backlog {source.issue_key}",
            )

    issue_keys = [by_id[item_id].issue_key for item_id in requested_ids]
    existing = list(
        (
            await session.scalars(
                select(Initiative)
                .options(selectinload(Initiative.executors))
                .where(
                    Initiative.cycle_id == cycle.id,
                    Initiative.issue_key.in_(issue_keys),
                )
            )
        ).all()
    )
    initiatives_by_key = {item.issue_key: item for item in existing}
    initiatives: list[Initiative] = []
    target = f"{cycle.year}-{cycle.quarter}"

    for sort_order, item_id in enumerate(requested_ids):
        source = by_id[item_id]
        initiative = initiatives_by_key.get(source.issue_key)
        if initiative is None:
            initiative = Initiative(
                id=uuid.uuid4(),
                cycle_id=cycle.id,
                issue_key=source.issue_key,
                executors=[],
            )
            session.add(initiative)
            initiatives_by_key[source.issue_key] = initiative
        initiative.backlog_item_id = source.id
        initiative.title = source.title
        initiative.description = source.description
        initiative.product = source.product
        initiative.owner_team_id = source.owner_team_id
        initiative.initiative_type = source.initiative_type
        initiative.customer_priority = source.customer_priority
        initiative.team_priority = source.team_priority
        initiative.status = "planned"
        initiative.sort_order = sort_order
        existing_executors = {
            executor.team_id: executor for executor in initiative.executors
        }
        initiative_executors: list[InitiativeExecutor] = []
        for executor in source.executors:
            record = existing_executors.get(executor.team_id)
            if record is None:
                record = InitiativeExecutor(team_id=executor.team_id)
            record.effort_by_competency = dict(executor.effort_by_competency or {})
            initiative_executors.append(record)
        initiative.executors = initiative_executors
        source.status = SENT_STATUS
        source.sent_to = _clean_unique([*(source.sent_to or []), target])
        initiatives.append(initiative)

    cycle.initiatives_initialized = True
    await session.commit()
    return BacklogDispatchRead(
        cycle_id=cycle.id,
        version=cycle.version,
        dispatched=len(initiatives),
        initiatives=[InitiativeRead.model_validate(item) for item in initiatives],
    )
