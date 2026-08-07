import re
import uuid

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    BacklogBoardState,
    BacklogExecutor,
    BacklogItem,
    Initiative,
    InitiativeAttraction,
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
from app.services.validation import (
    cycle_team_context,
    normalize_name,
    normalized_effort,
    resolve_cycle_team,
)


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
        super().__init__("Требуется подтверждение каскадных изменений")


class BacklogNotFound(ValueError):
    """The command references an entity outside the global backlog aggregate."""


def normalize_issue_key(raw: str) -> str:
    value = str(raw or "").strip()
    if not ISSUE_KEY_PATTERN.fullmatch(value):
        raise ValueError(
            "Issue должен начинаться с буквы или цифры и содержать только буквы, "
            "цифры, точки, подчёркивания или дефисы"
        )
    return value


def _clean_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def _board_executors(item: BacklogItem) -> list[BacklogExecutor]:
    """Return the resource row of the board that contains the backlog item."""
    return sorted(
        item.executors,
        key=lambda executor: (int(executor.sort_order or 0), str(executor.id)),
    )[:1]


def _item_effort(item: BacklogItem) -> float:
    total = 0.0
    for executor in _board_executors(item):
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


async def _reference_data(
    session: AsyncSession,
    cycle_id: uuid.UUID | None = None,
) -> BacklogReferenceDataRead:
    if cycle_id is not None:
        cycle_team_rows = list(
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
        tribes: list[Tribe] = []
        seen_tribes: set[uuid.UUID] = set()
        competency_codes: list[str] = []
        for cycle_team in cycle_team_rows:
            team = cycle_team.team
            if team.tribe and team.tribe.id not in seen_tribes:
                seen_tribes.add(team.tribe.id)
                tribes.append(team.tribe)
            for competency in cycle_team.competencies:
                code = competency.code.strip().upper()
                if code and code not in competency_codes:
                    competency_codes.append(code)
        return BacklogReferenceDataRead(
            tribes=[BacklogTribeRef(id=tribe.id, name=tribe.name) for tribe in tribes],
            teams=[
                BacklogTeamRef(
                    id=cycle_team.team.id,
                    tribe_id=cycle_team.team.tribe_id,
                    tribe=(
                        cycle_team.team.tribe.name if cycle_team.team.tribe else ""
                    ),
                    name=cycle_team.team.name,
                    competencies=[
                        value.code.strip().upper()
                        for value in cycle_team.competencies
                        if value.code.strip()
                    ],
                )
                for cycle_team in cycle_team_rows
            ],
            statuses=list(BACKLOG_STATUSES),
            competencies=competency_codes,
        )

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


async def read_backlog_board(
    session: AsyncSession,
    cycle_id: uuid.UUID | None = None,
) -> BacklogBoardRead:
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
                tshirt_size=item.tshirt_size or "",
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
                    for executor in _board_executors(item)
                ],
            )
        )
    return BacklogBoardRead(
        cycle_id=cycle_id,
        initialized=bool(marker and marker.initialized),
        version=marker.version if marker else 0,
        items=rows,
        reference_data=await _reference_data(session, cycle_id),
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
        raise ValueError(f"Неизвестный трайб: {value}")
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
        raise ValueError(f"Имя команды неоднозначно среди трайбов: {value}")
    raise ValueError(f"Неизвестная команда в трайбе {preferred_tribe.name}: {value}")


async def _apply_item_fields(
    session: AsyncSession,
    item: BacklogItem,
    source: BacklogItemFields,
    tribe_cache: dict[str, Tribe],
    team_cache: dict[tuple[str, uuid.UUID, bool], Team],
    cycle_context: tuple[
        dict[tuple[str, str], Team],
        dict[str, list[Team]],
        dict[uuid.UUID, set[str]],
    ]
    | None = None,
) -> None:
    issue_key = normalize_issue_key(source.issue_key)
    status = (source.status or "").strip() or "Нет оценки"
    if status not in BACKLOG_STATUSES:
        raise ValueError(f"Неизвестный статус бэклога: {status}")
    current_status = (item.status or "Нет оценки").strip()
    if status == SENT_STATUS and current_status != SENT_STATUS:
        raise ValueError("Статус «Отправлена в Pre PI Planning» можно задать только командой отправки на Pre PI Planning")
    if current_status == SENT_STATUS and status != SENT_STATUS:
        raise ValueError("Отправленную инициативу нельзя вернуть в редактируемый статус")
    if cycle_context is None:
        tribe = await _resolve_tribe(session, source.tribe, tribe_cache)
        owner = await _resolve_team(
            session, source.owner_team, tribe, team_cache, allow_cross_tribe=False
        )
        competencies_by_team: dict[uuid.UUID, set[str]] | None = None
    else:
        teams_by_key, teams_by_name, competencies_by_team = cycle_context
        tribe_key = normalize_name(source.tribe)
        tribe_teams = [
            team for (candidate_tribe, _), team in teams_by_key.items()
            if candidate_tribe == tribe_key
        ]
        if not tribe_teams or not tribe_teams[0].tribe:
            raise ValueError(f"Трайб не включён в данный PI-цикл: {source.tribe}")
        tribe = tribe_teams[0].tribe
        owner = (
            resolve_cycle_team(
                teams_by_key, teams_by_name, tribe.name, source.owner_team
            )
            if source.owner_team.strip()
            else None
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
    item.tshirt_size = source.tshirt_size
    item.tags = _clean_unique(source.tags)
    item.systems = _clean_unique(source.systems)

    existing_executors_by_id = {executor.id: executor for executor in item.executors}
    existing_executors = {executor.team_id: executor for executor in item.executors}
    executors: list[BacklogExecutor] = []
    executor_team_ids: set[uuid.UUID] = set()
    if len(source.executors) > 1:
        raise ValueError("В компетенциях владельца доски может быть только одна команда")
    for executor_order, executor in enumerate(source.executors):
        if cycle_context is None:
            team = await _resolve_team(
                session, executor.team, tribe, team_cache, allow_cross_tribe=True
            )
        else:
            team = resolve_cycle_team(
                teams_by_key, teams_by_name, "", executor.team
            )
        if team is None:
            continue
        if team.id in executor_team_ids:
            raise ValueError(
                f"Команда-исполнитель включена более одного раза для {issue_key}: {team.name}"
            )
        executor_team_ids.add(team.id)
        record = existing_executors_by_id.get(executor.id) if executor.id else None
        if executor.id is not None and record is None:
            raise BacklogNotFound(f"Исполнитель бэклога не найден: {executor.id}")
        if record is None:
            record = existing_executors.get(team.id)
        if record is None:
            record = BacklogExecutor(team_id=team.id)
        record.team_id = team.id
        record.sort_order = executor_order
        if competencies_by_team is None:
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
                value.code.strip().upper()
                for value in team.competencies
                if value.code.strip()
            }
            for cycle_team in configured:
                allowed_competencies.update(
                    value.code.strip().upper()
                    for value in cycle_team.competencies
                    if value.code.strip()
                )
        else:
            allowed_competencies = competencies_by_team[team.id]
        record.effort_by_competency = normalized_effort(
            executor.effort_by_competency,
            allowed_competencies,
            f"Бэклог {issue_key} / {team.name}",
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
    cycle_id: uuid.UUID | None = None,
) -> None:
    issue_key = normalize_issue_key(payload.issue_key)
    if await session.scalar(
        select(BacklogItem).where(func.lower(BacklogItem.issue_key) == issue_key.casefold())
    ):
        raise ValueError(f"Такой Issue уже существует в глобальном бэклоге: {issue_key}")
    item = BacklogItem(
        id=uuid.uuid4(),
        issue_key=issue_key,
        title=payload.title.strip(),
        executors=[],
        sort_order=await _next_sort_order(session),
    )
    session.add(item)
    await session.flush()
    cycle_context = await cycle_team_context(session, cycle_id) if cycle_id else None
    await _apply_item_fields(session, item, payload, {}, {}, cycle_context)
    await _mark_board_initialized(session)


async def update_backlog_item(
    session: AsyncSession,
    item_id: uuid.UUID,
    payload: BacklogItemCommand,
    cycle_id: uuid.UUID | None = None,
) -> None:
    item = await session.scalar(
        select(BacklogItem)
        .options(selectinload(BacklogItem.executors))
        .where(BacklogItem.id == item_id)
    )
    if item is None:
        raise BacklogNotFound("Элемент бэклога не найден")
    issue_key = normalize_issue_key(payload.issue_key)
    duplicate = await session.scalar(
        select(BacklogItem).where(
            BacklogItem.id != item_id,
            func.lower(BacklogItem.issue_key) == issue_key.casefold(),
        )
    )
    if duplicate is not None:
        raise ValueError(f"Такой Issue уже существует в глобальном бэклоге: {issue_key}")
    cycle_context = await cycle_team_context(session, cycle_id) if cycle_id else None
    await _apply_item_fields(session, item, payload, {}, {}, cycle_context)
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
        raise BacklogNotFound("Элемент бэклога не найден")
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
        raise ValueError("Элемент встречается в команде изменения порядка более одного раза")
    if set(ordered_ids) != set(by_id):
        raise ValueError("Команда изменения порядка должна содержать все элементы бэклога ровно по одному разу")
    for order, item_id in enumerate(ordered_ids):
        by_id[item_id].sort_order = order
    await _mark_board_initialized(session)


async def replace_backlog_board(
    session: AsyncSession,
    payload: BacklogBoardWrite,
    cycle_id: uuid.UUID | None = None,
) -> None:
    normalized_keys = [normalize_issue_key(item.issue_key).casefold() for item in payload.items]
    if len(normalized_keys) != len(set(normalized_keys)):
        raise ValueError("Issue должен быть уникален в пределах глобального бэклога")

    existing = await _items_query(session)
    by_id = {item.id: item for item in existing}
    by_key = {item.issue_key.casefold(): item for item in existing}
    used_ids: set[uuid.UUID] = set()
    tribe_cache: dict[str, Tribe] = {}
    team_cache: dict[tuple[str, uuid.UUID, bool], Team] = {}
    cycle_context = await cycle_team_context(session, cycle_id) if cycle_id else None

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
            raise ValueError(f"Элемент бэклога не найден: {source.id}")
        if item is None:
            item = key_match
        if item is not None and item.id in used_ids:
            raise ValueError(f"Элемент бэклога включён более одного раза: {issue_key}")
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

        await _apply_item_fields(
            session, item, source, tribe_cache, team_cache, cycle_context
        )
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
            f"PI-цикл {target_key} ещё не создан — сначала откройте его на вкладке «Данные PI-цикла»"
        )

    tribe = await session.scalar(
        select(Tribe).where(func.lower(Tribe.name) == payload.tribe.strip().casefold())
    )
    if tribe is None:
        raise ValueError(f"Неизвестный трайб: {payload.tribe}")

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
            f"Нет инициатив для трайба {payload.tribe} с периодом реализации {target_key}"
        )

    _, _, competencies_by_team = await cycle_team_context(session, target.id)
    for source in candidates:
        if source.owner_team_id is not None and source.owner_team_id not in competencies_by_team:
            raise ValueError(
                f"Команда-владелец не входит в {target_key} для {source.issue_key}"
            )
        board_executors = _board_executors(source)
        for executor in board_executors:
            if executor.team_id not in competencies_by_team:
                raise ValueError(
                    f"Команда-исполнитель не входит в {target_key} для {source.issue_key}"
                )
            # Reject backlog effort that references a competency the cycle team does not own.
            normalized_effort(
                executor.effort_by_competency or {},
                competencies_by_team[executor.team_id],
                f"Бэклог {source.issue_key} / отправка",
            )

    candidate_ids = {item.id for item in candidates}
    issue_keys = {item.issue_key.casefold() for item in candidates}
    existing_initiatives = list(
        (
            await session.scalars(
                select(Initiative)
                .options(selectinload(Initiative.executors))
                .where(
                    Initiative.cycle_id == target.id,
                    or_(
                        Initiative.backlog_item_id.in_(candidate_ids),
                        func.lower(Initiative.issue_key).in_(issue_keys),
                    ),
                )
            )
        ).all()
    )
    initiatives_by_backlog_id = {
        item.backlog_item_id: item
        for item in existing_initiatives
        if item.backlog_item_id is not None
    }
    initiatives_by_key = {
        item.issue_key.casefold(): item for item in existing_initiatives
    }
    max_sort_order = await session.scalar(
        select(func.max(Initiative.sort_order)).where(
            Initiative.cycle_id == target.id
        )
    )
    next_sort_order = int(max_sort_order if max_sort_order is not None else -1) + 1
    assignments: list[tuple[BacklogItem, Initiative, bool]] = []
    assigned_ids: set[uuid.UUID] = set()
    conflicts: list[str] = []
    for source in candidates:
        linked = initiatives_by_backlog_id.get(source.id)
        keyed = initiatives_by_key.get(source.issue_key.casefold())
        initiative = linked
        if linked is not None and keyed is not None and keyed.id != linked.id:
            if keyed.backlog_item_id not in candidate_ids:
                conflicts.append(source.issue_key)
        elif linked is None and keyed is not None:
            if keyed.backlog_item_id is None:
                initiative = keyed
            elif keyed.backlog_item_id not in candidate_ids:
                conflicts.append(source.issue_key)
        is_new = initiative is None
        if is_new:
            initiative = Initiative(
                id=uuid.uuid4(),
                cycle_id=target.id,
                issue_key=f"__pre_pi_sync_{uuid.uuid4().hex}",
                title=source.title,
                status="planned",
                pre_planned=False,
                sort_order=next_sort_order,
                executors=[],
            )
            next_sort_order += 1
            session.add(initiative)
        if initiative.id in assigned_ids:
            conflicts.append(source.issue_key)
        assigned_ids.add(initiative.id)
        assignments.append((source, initiative, is_new))
    if conflicts:
        raise ValueError(
            "PI-цикл уже содержит инициативы, связанные с другим элементом бэклога: "
            + ", ".join(sorted(set(conflicts)))
        )

    # Освобождаем уникальные Issue перед поддерживаемыми UUID-стабильными
    # переименованиями и перестановками ключей между уже отправленными строками.
    for source, initiative, is_new in assignments:
        if not is_new and initiative.issue_key != source.issue_key:
            initiative.issue_key = f"__pre_pi_sync_{initiative.id.hex}"
    await session.flush()

    for source, initiative, _ in assignments:
        initiative.backlog_item_id = source.id
        initiative.issue_key = source.issue_key
        initiative.title = source.title
        initiative.description = source.description
        initiative.product = source.product
        initiative.owner_team_id = source.owner_team_id
        initiative.initiative_type = source.initiative_type
        initiative.tshirt_size = source.tshirt_size
        initiative.customer_priority = source.customer_priority
        initiative.team_priority = source.team_priority
        initiative.tags = list(source.tags or [])
        initiative.generated_from_attraction = False
        existing_executors = sorted(
            initiative.executors,
            key=lambda executor: (executor.sort_order, str(executor.id)),
        )[:1]
        initiative_executors: list[InitiativeExecutor] = []
        # Keep one resource row for the board that owns this planning view. For
        # legacy items without such a row, the task owner's team is the safe default.
        source_executors = _board_executors(source)
        if source.owner_team_id is not None and not source_executors:
            source_executors = [BacklogExecutor(team_id=source.owner_team_id, effort_by_competency={})]
        for executor in source_executors:
            record = existing_executors[0] if existing_executors else None
            if record is None:
                record = InitiativeExecutor(team_id=executor.team_id)
            record.team_id = executor.team_id
            record.effort_by_competency = dict(executor.effort_by_competency or {})
            record.sort_order = 0
            initiative_executors.append(record)
        initiative.executors = initiative_executors
        await session.execute(
            update(InitiativeAttraction)
            .where(InitiativeAttraction.target_initiative_id == initiative.id)
            .values(issue_key=source.issue_key)
        )
        source.status = SENT_STATUS
        source.sent_to = _clean_unique([*(source.sent_to or []), target_key])

    target.initiatives_initialized = True
    target.version += 1
    await _mark_board_initialized(session)
