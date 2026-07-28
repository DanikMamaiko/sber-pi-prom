import re
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    BacklogBoardState,
    BacklogExecutor,
    BacklogItem,
    Initiative,
    InitiativeExecutor,
    PiCycle,
    PiCycleTeam,
    Team,
    Tribe,
)
from app.schemas.pi_cycle import (
    BacklogBoardItemRead,
    BacklogBoardRead,
    BacklogBoardWrite,
    BacklogDispatchWrite,
    BacklogItemCommand,
    BacklogItemDelete,
    BacklogItemFields,
    BacklogReorderCommand,
    BacklogReferenceDataRead,
    BacklogTeamRef,
    BacklogTribeRef,
)
from app.services.validation import cycle_team_context, normalized_effort


BACKLOG_STATE_ID = 1
SENT_STATUS = "Отправлена в Pre PI Planning"
BACKLOG_STATUSES = ["Нет оценки", "Оценка проведена", SENT_STATUS]
COMPETENCIES = ["SA", "DEV", "QA", "FE", "BE", "DES"]
ISSUE_KEY_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9._-]{0,79}$")


class BacklogCascadeRequired(ValueError):
    """A backlog write touches related PI-cycle data and needs confirmation."""

    def __init__(self, entity: str, affected: dict[str, int]):
        self.detail = {
            "code": "cascade_confirmation_required",
            "entity": entity,
            "affected": affected,
        }
        super().__init__("Cascade confirmation is required")


class BacklogNotFound(ValueError):
    """The command references an entity outside the global backlog aggregate."""


def normalize_issue_key(raw: str) -> str:
    value = str(raw or "").strip()
    if not ISSUE_KEY_PATTERN.fullmatch(value):
        raise ValueError(
            "Issue ID must start with a letter or digit and contain only letters, "
            "digits, dots, underscores or hyphens"
        )
    return value


def _clean_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def _item_effort(item: BacklogItem) -> float:
    total = 0.0
    for executor in item.executors:
        for value in (executor.effort_by_competency or {}).values():
            try:
                total += float(value)
            except (TypeError, ValueError):
                continue
    return round(total, 3)


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


async def _reference_data(session: AsyncSession) -> BacklogReferenceDataRead:
    tribes = list(
        (await session.scalars(select(Tribe).order_by(Tribe.name, Tribe.id))).all()
    )
    team_rows = list(
        (
            await session.scalars(
                select(Team)
                .options(
                    selectinload(Team.tribe),
                    selectinload(Team.competencies),
                )
                .order_by(Tribe.name, Team.name, Team.id)
                .join(Tribe, Team.tribe_id == Tribe.id)
            )
        ).all()
    )
    cycle_team_rows = list(
        (
            await session.scalars(
                select(PiCycleTeam).options(selectinload(PiCycleTeam.competencies))
            )
        ).all()
    )
    configured_competencies: dict[uuid.UUID, set[str]] = {}
    for cycle_team in cycle_team_rows:
        configured_competencies.setdefault(cycle_team.team_id, set()).update(
            value.code.strip().upper()
            for value in cycle_team.competencies
            if value.code.strip()
        )
    return BacklogReferenceDataRead(
        tribes=[BacklogTribeRef(id=tribe.id, name=tribe.name) for tribe in tribes],
        teams=[
            BacklogTeamRef(
                id=team.id,
                tribe_id=team.tribe_id,
                tribe=team.tribe.name if team.tribe else "",
                name=team.name,
                competencies=[
                    code
                    for code in COMPETENCIES
                    if code
                    in {
                        *(competency.code.strip().upper() for competency in team.competencies),
                        *configured_competencies.get(team.id, set()),
                    }
                ],
            )
            for team in team_rows
        ],
        statuses=list(BACKLOG_STATUSES),
        competencies=list(COMPETENCIES),
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
                tags=list(item.tags or []),
                sent_to=list(item.sent_to or []),
                sort_order=item.sort_order,
                total_effort=_item_effort(item),
                executors=[
                    {
                        "id": executor.id,
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
        reference_data=await _reference_data(session),
    )


async def _resolve_tribe(
    session: AsyncSession,
    name: str,
    cache: dict[str, Tribe],
) -> Tribe:
    value = name.strip()
    if value in cache:
        return cache[value]
    tribe = await session.scalar(
        select(Tribe).where(func.lower(Tribe.name) == value.casefold())
    )
    if tribe is None:
        raise ValueError(f"Unknown tribe: {value}")
    cache[value] = tribe
    return tribe


async def _resolve_team(
    session: AsyncSession,
    name: str,
    preferred_tribe: Tribe,
    cache: dict[tuple[str, uuid.UUID, bool], Team],
    *,
    allow_cross_tribe: bool,
) -> Team | None:
    value = name.strip()
    if not value:
        return None
    key = (value.casefold(), preferred_tribe.id, allow_cross_tribe)
    if key in cache:
        return cache[key]
    teams = list(
        (
            await session.scalars(
                select(Team)
                .options(selectinload(Team.competencies))
                .where(func.lower(Team.name) == value.casefold())
            )
        ).all()
    )
    preferred = next((team for team in teams if team.tribe_id == preferred_tribe.id), None)
    if preferred:
        cache[key] = preferred
        return preferred
    if allow_cross_tribe and len(teams) == 1:
        cache[key] = teams[0]
        return teams[0]
    if len(teams) > 1:
        raise ValueError(f"Team name is ambiguous across tribes: {value}")
    raise ValueError(f"Unknown team in tribe {preferred_tribe.name}: {value}")


async def _apply_item_fields(
    session: AsyncSession,
    item: BacklogItem,
    source: BacklogItemFields,
    tribe_cache: dict[str, Tribe],
    team_cache: dict[tuple[str, uuid.UUID, bool], Team],
) -> None:
    issue_key = normalize_issue_key(source.issue_key)
    status = (source.status or "").strip() or "Нет оценки"
    if status not in BACKLOG_STATUSES:
        raise ValueError(f"Unknown backlog status: {status}")
    current_status = (item.status or "Нет оценки").strip()
    if status == SENT_STATUS and current_status != SENT_STATUS:
        raise ValueError("Sent status can only be assigned by the dispatch command")
    if current_status == SENT_STATUS and status != SENT_STATUS:
        raise ValueError("A dispatched initiative cannot be returned to an editable status")
    tribe = await _resolve_tribe(session, source.tribe, tribe_cache)
    owner = await _resolve_team(
        session, source.owner_team, tribe, team_cache, allow_cross_tribe=False
    )

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
    item.status = status
    item.tags = _clean_unique(source.tags)
    item.systems = _clean_unique(source.systems)

    existing_executors_by_id = {executor.id: executor for executor in item.executors}
    existing_executors = {executor.team_id: executor for executor in item.executors}
    executors: list[BacklogExecutor] = []
    executor_team_ids: set[uuid.UUID] = set()
    for executor_order, executor in enumerate(source.executors):
        team = await _resolve_team(
            session, executor.team, tribe, team_cache, allow_cross_tribe=True
        )
        if team is None:
            continue
        if team.id in executor_team_ids:
            raise ValueError(
                f"Executor team is included more than once for {issue_key}: {team.name}"
            )
        executor_team_ids.add(team.id)
        record = existing_executors_by_id.get(executor.id) if executor.id else None
        if executor.id is not None and record is None:
            raise BacklogNotFound(f"Backlog executor ID is not found: {executor.id}")
        if record is None:
            record = existing_executors.get(team.id)
        if record is None:
            record = BacklogExecutor(team_id=team.id)
        record.team_id = team.id
        record.sort_order = executor_order
        configured = list(
            (
                await session.scalars(
                    select(PiCycleTeam)
                    .where(PiCycleTeam.team_id == team.id)
                    .options(selectinload(PiCycleTeam.competencies))
                )
            ).all()
        )
        allowed_competencies = {
            value.code.strip().upper() for value in team.competencies if value.code.strip()
        }
        for cycle_team in configured:
            allowed_competencies.update(
                value.code.strip().upper()
                for value in cycle_team.competencies
                if value.code.strip()
            )
        record.effort_by_competency = normalized_effort(
            executor.effort_by_competency,
            allowed_competencies,
            f"Backlog {issue_key} / {team.name}",
        )
        executors.append(record)
    item.executors = executors


async def _next_sort_order(session: AsyncSession) -> int:
    current = await session.scalar(select(func.max(BacklogItem.sort_order)))
    return int(current if current is not None else -1) + 1


async def _mark_board_initialized(session: AsyncSession) -> None:
    marker = await session.get(BacklogBoardState, BACKLOG_STATE_ID)
    if marker is None:
        marker = BacklogBoardState(id=BACKLOG_STATE_ID, initialized=True)
        session.add(marker)
    else:
        marker.initialized = True
    await session.flush()


async def create_backlog_item(
    session: AsyncSession,
    payload: BacklogItemCommand,
) -> None:
    issue_key = normalize_issue_key(payload.issue_key)
    if await session.scalar(
        select(BacklogItem).where(func.lower(BacklogItem.issue_key) == issue_key.casefold())
    ):
        raise ValueError(f"Issue ID already exists in the global backlog: {issue_key}")
    item = BacklogItem(
        id=uuid.uuid4(),
        issue_key=issue_key,
        title=payload.title.strip(),
        executors=[],
        sort_order=await _next_sort_order(session),
    )
    session.add(item)
    await session.flush()
    await _apply_item_fields(session, item, payload, {}, {})
    await _mark_board_initialized(session)


async def update_backlog_item(
    session: AsyncSession,
    item_id: uuid.UUID,
    payload: BacklogItemCommand,
) -> None:
    item = await session.scalar(
        select(BacklogItem)
        .options(selectinload(BacklogItem.executors))
        .where(BacklogItem.id == item_id)
    )
    if item is None:
        raise BacklogNotFound("Backlog item not found")
    issue_key = normalize_issue_key(payload.issue_key)
    duplicate = await session.scalar(
        select(BacklogItem).where(
            BacklogItem.id != item_id,
            func.lower(BacklogItem.issue_key) == issue_key.casefold(),
        )
    )
    if duplicate is not None:
        raise ValueError(f"Issue ID already exists in the global backlog: {issue_key}")
    await _apply_item_fields(session, item, payload, {}, {})
    await _mark_board_initialized(session)


async def _unlink_dispatched_initiatives(
    session: AsyncSession,
    item_ids: list[uuid.UUID],
) -> int:
    cycle_ids = list(
        (
            await session.scalars(
                select(Initiative.cycle_id)
                .where(Initiative.backlog_item_id.in_(item_ids))
                .distinct()
                .order_by(Initiative.cycle_id)
            )
        ).all()
    )
    if cycle_ids:
        cycles = list(
            (
                await session.scalars(
                    select(PiCycle)
                    .where(PiCycle.id.in_(cycle_ids))
                    .order_by(PiCycle.id)
                    .with_for_update()
                )
            ).all()
        )
        for cycle in cycles:
            cycle.version += 1
        await session.execute(
            update(Initiative)
            .where(Initiative.backlog_item_id.in_(item_ids))
            .values(backlog_item_id=None)
        )
    return len(cycle_ids)


async def delete_backlog_item(
    session: AsyncSession,
    item_id: uuid.UUID,
    payload: BacklogItemDelete,
) -> None:
    item = await session.scalar(select(BacklogItem).where(BacklogItem.id == item_id))
    if item is None:
        raise BacklogNotFound("Backlog item not found")
    dispatched_links = int(
        await session.scalar(
            select(func.count())
            .select_from(Initiative)
            .where(Initiative.backlog_item_id == item_id)
        )
        or 0
    )
    if dispatched_links and not payload.confirm_cascade:
        raise BacklogCascadeRequired(
            "backlog_item", {"dispatched_links": dispatched_links}
        )
    if dispatched_links:
        # A dispatched PI initiative is an independent planning copy. Removing the
        # source row unlinks (not deletes) the copy, and only with confirmation.
        await _unlink_dispatched_initiatives(session, [item_id])
    await session.delete(item)
    await _mark_board_initialized(session)


async def reorder_backlog_items(
    session: AsyncSession,
    payload: BacklogReorderCommand,
) -> None:
    items = list((await session.scalars(select(BacklogItem))).all())
    by_id = {item.id: item for item in items}
    ordered_ids = list(dict.fromkeys(payload.item_ids))
    if len(ordered_ids) != len(payload.item_ids):
        raise ValueError("An item appears more than once in the reorder command")
    if set(ordered_ids) != set(by_id):
        raise ValueError("Reorder command must list every backlog item exactly once")
    for order, item_id in enumerate(ordered_ids):
        by_id[item_id].sort_order = order
    await _mark_board_initialized(session)


async def replace_backlog_board(
    session: AsyncSession,
    payload: BacklogBoardWrite,
) -> None:
    normalized_keys = [normalize_issue_key(item.issue_key).casefold() for item in payload.items]
    if len(normalized_keys) != len(set(normalized_keys)):
        raise ValueError("Issue ID must be unique across the global backlog")

    existing = await _items_query(session)
    by_id = {item.id: item for item in existing}
    by_key = {item.issue_key.casefold(): item for item in existing}
    used_ids: set[uuid.UUID] = set()
    tribe_cache: dict[str, Tribe] = {}
    team_cache: dict[tuple[str, uuid.UUID, bool], Team] = {}

    # Clear the unique namespace inside this transaction so UUID-stable swaps
    # such as ABC-1 <-> ABC-2 are not rejected by PostgreSQL mid-flush.
    for item in existing:
        item.issue_key = f"__backlog_swap_{item.id.hex}"
    if existing:
        await session.flush()

    applied_by_index: dict[int, BacklogItem] = {}
    for position, source in enumerate(payload.items):
        issue_key = normalize_issue_key(source.issue_key)
        item = by_id.get(source.id) if source.id else None
        key_match = by_key.get(issue_key.casefold())
        if source.id is not None and item is None:
            raise ValueError(f"Backlog item ID is not found: {source.id}")
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
        applied_by_index[position] = item

        await _apply_item_fields(session, item, source, tribe_cache, team_cache)
        item.sort_order = source.sort_order if source.sort_order is not None else position

    removed_ids = [item.id for item in existing if item.id not in used_ids]
    if removed_ids:
        links = int(
            await session.scalar(
                select(func.count())
                .select_from(Initiative)
                .where(Initiative.backlog_item_id.in_(removed_ids))
            )
            or 0
        )
        if links and not payload.confirm_cascade:
            raise BacklogCascadeRequired(
                "backlog_item",
                {"dispatched_links": links, "items_removed": len(removed_ids)},
            )
        if links:
            await _unlink_dispatched_initiatives(session, removed_ids)
        for item in existing:
            if item.id in removed_ids:
                await session.delete(item)

    ordered = sorted(
        enumerate(payload.items), key=lambda pair: (pair[1].sort_order, pair[0])
    )
    for order, (source_index, _) in enumerate(ordered):
        applied_by_index[source_index].sort_order = order
    await _mark_board_initialized(session)


async def dispatch_backlog_items(
    session: AsyncSession,
    payload: BacklogDispatchWrite,
) -> None:
    """Atomically move a tribe's matching initiatives into a target PI-cycle.

    Touches two aggregates: it marks backlog items as sent (backlog version) and
    creates PI-cycle initiative copies (target cycle). Both happen in one
    transaction; the backlog lock serializes the command against every other
    backlog write.
    """

    target_key = f"{payload.target_year}-{payload.target_quarter}"
    target = await session.scalar(
        select(PiCycle)
        .where(
            PiCycle.year == payload.target_year,
            PiCycle.quarter == payload.target_quarter,
        )
        .with_for_update()
    )
    if target is None:
        raise ValueError(
            f"PI cycle {target_key} is not created yet — open it on «Данные PI-цикла» first"
        )

    tribe = await session.scalar(
        select(Tribe).where(func.lower(Tribe.name) == payload.tribe.strip().casefold())
    )
    if tribe is None:
        raise ValueError(f"Unknown tribe: {payload.tribe}")

    candidates = list(
        (
            await session.scalars(
                select(BacklogItem)
                .options(selectinload(BacklogItem.executors))
                .where(
                    BacklogItem.tribe_id == tribe.id,
                    BacklogItem.target_year == payload.target_year,
                    BacklogItem.target_quarter == payload.target_quarter,
                )
                .order_by(BacklogItem.sort_order, BacklogItem.created_at, BacklogItem.id)
            )
        ).all()
    )
    if not candidates:
        raise ValueError(
            f"No initiatives for {payload.tribe} with realization period {target_key}"
        )

    already_sent = [
        item.issue_key for item in candidates if target_key in (item.sent_to or [])
    ]
    if already_sent:
        raise ValueError(
            f"Initiatives are already dispatched to {target_key}: "
            f"{', '.join(already_sent)}"
        )

    _, _, competencies_by_team = await cycle_team_context(session, target.id)
    for source in candidates:
        if source.owner_team_id is not None and source.owner_team_id not in competencies_by_team:
            raise ValueError(
                f"Owner team is not part of {target_key} for {source.issue_key}"
            )
        for executor in source.executors:
            if executor.team_id not in competencies_by_team:
                raise ValueError(
                    f"Executor team is not part of {target_key} for {source.issue_key}"
                )
            # Reject backlog effort that references a competency the cycle team does not own.
            normalized_effort(
                executor.effort_by_competency or {},
                competencies_by_team[executor.team_id],
                f"Backlog {source.issue_key} / dispatch",
            )

    issue_keys = [item.issue_key for item in candidates]
    existing_initiatives = list(
        (
            await session.scalars(
                select(Initiative)
                .options(selectinload(Initiative.executors))
                .where(
                    Initiative.cycle_id == target.id,
                    Initiative.issue_key.in_(issue_keys),
                )
            )
        ).all()
    )
    initiatives_by_key = {item.issue_key: item for item in existing_initiatives}

    conflicts = [
        item.issue_key
        for item in existing_initiatives
        if item.backlog_item_id is not None
        and item.backlog_item_id
        != next(row.id for row in candidates if row.issue_key == item.issue_key)
    ]
    if conflicts:
        raise ValueError(
            "PI cycle already contains initiatives linked to another backlog item: "
            + ", ".join(conflicts)
        )

    for sort_order, source in enumerate(candidates):
        initiative = initiatives_by_key.get(source.issue_key)
        if initiative is None:
            initiative = Initiative(
                id=uuid.uuid4(),
                cycle_id=target.id,
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
        initiative.tags = list(source.tags or [])
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
        source.sent_to = _clean_unique([*(source.sent_to or []), target_key])

    target.initiatives_initialized = True
    target.version += 1
    await _mark_board_initialized(session)
