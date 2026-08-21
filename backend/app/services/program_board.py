import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    BoardConnection,
    Initiative,
    InitiativeExecutor,
    PiEvent,
    PiCycle,
    PiCycleTeam,
    Story,
    Team,
    WorkItem,
)
from app.schemas.pi_cycle import (
    ProgramBoardConnectionCreate,
    ProgramBoardConnectionRead,
    ProgramBoardConnectionUpdate,
    ProgramBoardMoveCommand,
    ProgramBoardRead,
    ProgramBoardWrite,
)
from app.services.validation import validate_sprint_position


async def _endpoint_maps(
    session: AsyncSession,
    cycle_id: uuid.UUID,
) -> tuple[
    dict[str, Initiative],
    dict[uuid.UUID, Initiative],
    dict[str, Story],
    dict[uuid.UUID, Story],
    dict[str, WorkItem],
    dict[uuid.UUID, WorkItem],
]:
    initiatives = list(
        (
            await session.scalars(
                select(Initiative).where(Initiative.cycle_id == cycle_id)
            )
        ).all()
    )
    work_items = list(
        (
            await session.scalars(
                select(WorkItem)
                .join(Initiative, Initiative.id == WorkItem.initiative_id)
                .where(Initiative.cycle_id == cycle_id)
            )
        ).all()
    )
    stories = list(
        (
            await session.scalars(
                select(Story)
                .join(Initiative, Initiative.id == Story.initiative_id)
                .where(Initiative.cycle_id == cycle_id)
            )
        ).all()
    )
    return (
        {row.issue_key.casefold(): row for row in initiatives},
        {row.id: row for row in initiatives},
        {row.client_uid.casefold(): row for row in stories},
        {row.id: row for row in stories},
        {row.client_uid.casefold(): row for row in work_items},
        {row.id: row for row in work_items},
    )


def _endpoint_ref(
    kind: str,
    endpoint_id: uuid.UUID,
    initiatives: dict[uuid.UUID, Initiative],
    stories: dict[uuid.UUID, Story],
    work_items: dict[uuid.UUID, WorkItem],
) -> dict[str, str] | None:
    if kind in {"initiative", "c"}:
        initiative = initiatives.get(endpoint_id)
        return {"kind": "c", "ref": initiative.issue_key} if initiative else None
    if kind in {"story", "g"}:
        story = stories.get(endpoint_id)
        return {"kind": "g", "ref": story.client_uid} if story else None
    if kind in {"work_item", "w"}:
        item = work_items.get(endpoint_id)
        return {"kind": "w", "ref": item.client_uid} if item else None
    return None


async def read_program_board(
    session: AsyncSession,
    cycle: PiCycle,
) -> ProgramBoardRead:
    cycle_teams = list(
        (
            await session.scalars(
                select(PiCycleTeam)
                .options(selectinload(PiCycleTeam.team).selectinload(Team.tribe))
                .where(PiCycleTeam.cycle_id == cycle.id)
                .order_by(PiCycleTeam.sort_order, PiCycleTeam.id)
            )
        ).all()
    )
    active_team_ids = {row.team_id for row in cycle_teams}
    initiatives_rows = list(
        (
            await session.scalars(
                select(Initiative)
                .execution_options(populate_existing=True)
                .options(
                    selectinload(Initiative.owner_team),
                    selectinload(Initiative.executors)
                    .selectinload(InitiativeExecutor.team)
                    .selectinload(Team.tribe),
                )
                .where(Initiative.cycle_id == cycle.id)
                .order_by(Initiative.sort_order, Initiative.created_at, Initiative.id)
            )
        ).all()
    )
    initiatives = {row.id: row for row in initiatives_rows}
    stories_rows = list(
        (
            await session.scalars(
                select(Story)
                .join(Initiative, Initiative.id == Story.initiative_id)
                .where(Initiative.cycle_id == cycle.id)
            )
        ).all()
    )
    stories = {row.id: row for row in stories_rows}
    work_items_rows = list(
        (
            await session.scalars(
                select(WorkItem)
                .join(Initiative, Initiative.id == WorkItem.initiative_id)
                .where(Initiative.cycle_id == cycle.id)
            )
        ).all()
    )
    work_items = {row.id: row for row in work_items_rows}
    connections = list(
        (
            await session.scalars(
                select(BoardConnection)
                .where(BoardConnection.cycle_id == cycle.id)
                .order_by(
                    BoardConnection.sort_order,
                    BoardConnection.created_at,
                    BoardConnection.id,
                )
            )
        ).all()
    )
    rows: list[ProgramBoardConnectionRead] = []
    conflicts: list[dict] = []
    card_conflicts: dict[uuid.UUID, list[str]] = {}
    for connection in connections:
        source = _endpoint_ref(
            connection.source_kind,
            connection.source_id,
            initiatives,
            stories,
            work_items,
        )
        target = _endpoint_ref(
            connection.target_kind,
            connection.target_id,
            initiatives,
            stories,
            work_items,
        )
        if source is None or target is None:
            continue
        bend = None
        if connection.bend_dx is not None or connection.bend_dy is not None:
            bend = {
                "dx": float(connection.bend_dx or 0),
                "dy": float(connection.bend_dy or 0),
            }
        rows.append(
            ProgramBoardConnectionRead(
                id=connection.id,
                client_uid=connection.client_uid,
                source=source,
                target=target,
                relation_type=connection.relation_type,
                bend=bend,
                sort_order=connection.sort_order,
            )
        )

        def endpoint_sprint(kind: str, endpoint_id: uuid.UUID) -> int | None:
            if kind in {"initiative", "c"}:
                entity = initiatives.get(endpoint_id)
            elif kind in {"story", "g"}:
                entity = stories.get(endpoint_id)
            else:
                entity = work_items.get(endpoint_id)
            return entity.sprint_index if entity else None

        source_sprint = endpoint_sprint(connection.source_kind, connection.source_id)
        target_sprint = endpoint_sprint(connection.target_kind, connection.target_id)
        if source_sprint is None or target_sprint is None:
            conflicts.append(
                {
                    "code": "unscheduled_dependency",
                    "message": (
                        f"Проверьте связь {source['ref']} -> {target['ref']}: "
                        "у одной из работ не выбран спринт"
                    ),
                    "connection_id": connection.id,
                }
            )

    team_rows = []
    tribe_rows = []
    seen_tribes: set[uuid.UUID] = set()
    team_sort: dict[uuid.UUID, int] = {}
    for position, cycle_team in enumerate(cycle_teams):
        team = cycle_team.team
        tribe = team.tribe
        team_sort[team.id] = position
        if tribe.id not in seen_tribes:
            seen_tribes.add(tribe.id)
            tribe_rows.append(
                {"id": tribe.id, "name": tribe.name, "sort_order": len(tribe_rows)}
            )
        team_rows.append(
            {
                "id": team.id,
                "tribe_id": tribe.id,
                "tribe": tribe.name,
                "name": team.name,
                "sort_order": position,
            }
        )

    cards = []
    for initiative in initiatives_rows:
        if not initiative.on_board:
            continue
        executors = sorted(
            initiative.executors, key=lambda row: (row.sort_order, str(row.id))
        )
        primary = executors[0] if executors else None
        if primary is None or primary.team_id not in active_team_ids:
            conflicts.append(
                {
                    "code": "missing_active_executor",
                    "severity": "error",
                    "message": f"Инициатива {initiative.issue_key} не имеет исполнителя активного PI",
                    "initiative_id": initiative.id,
                }
            )
            continue
        codes = card_conflicts.setdefault(initiative.id, [])
        if initiative.sprint_index is None:
            codes.append("unscheduled_initiative")
            conflicts.append(
                {
                    "code": "unscheduled_initiative",
                    "message": f"Инициатива {initiative.issue_key} не назначена на спринт",
                    "initiative_id": initiative.id,
                }
            )
        elif initiative.sprint_index < 0 or initiative.sprint_index >= cycle.sprint_count:
            codes.append("sprint_out_of_range")
            conflicts.append(
                {
                    "code": "sprint_out_of_range",
                    "severity": "error",
                    "message": f"Инициатива {initiative.issue_key} находится вне спринтов PI",
                    "initiative_id": initiative.id,
                }
            )
        owner_name = initiative.owner_team.name if initiative.owner_team else ""
        executor_rows = []
        total = 0.0
        for executor in executors:
            if executor.team_id not in active_team_ids:
                continue
            effort = {
                str(key): float(value or 0)
                for key, value in dict(executor.effort_by_competency or {}).items()
            }
            executor_total = sum(effort.values())
            total += executor_total
            executor_rows.append(
                {
                    "team_id": executor.team_id,
                    "team": executor.team.name,
                    "effort_by_competency": effort,
                    "total_effort": executor_total,
                }
            )
        visual_state = (
            "blue"
            if initiative.owner_team_id in {None, primary.team_id}
            else ("red" if initiative.agreed else "purple")
        )
        cards.append(
            {
                "id": initiative.id,
                "issue_key": initiative.issue_key,
                "title": initiative.title,
                "initiative_type": initiative.initiative_type or "",
                "owner_team_id": initiative.owner_team_id,
                "owner_team": owner_name,
                "primary_team_id": primary.team_id,
                "primary_team": primary.team.name,
                "primary_tribe_id": primary.team.tribe.id,
                "primary_tribe": primary.team.tribe.name,
                "executors": executor_rows,
                "tags": list(initiative.tags or []),
                "sprint_index": initiative.sprint_index,
                "week_index": initiative.week_index,
                "board_sort_order": initiative.board_sort_order,
                "agreed": initiative.agreed,
                "visual_state": visual_state,
                "total_effort": total,
                "conflict_codes": codes,
            }
        )
    cards.sort(
        key=lambda row: (
            team_sort.get(row["primary_team_id"], 10**9),
            row["sprint_index"] if row["sprint_index"] is not None else 10**9,
            row["board_sort_order"],
            row["issue_key"].casefold(),
        )
    )

    sprints = []
    if cycle.start_date:
        sorted_events = list(
            (
                await session.scalars(
                    select(PiEvent)
                    .where(PiEvent.cycle_id == cycle.id)
                    .order_by(PiEvent.event_date, PiEvent.sort_order, PiEvent.id)
                )
            ).all()
        )
        for index in range(max(0, cycle.sprint_count)):
            start = cycle.start_date + timedelta(days=index * 14)
            end = start + timedelta(days=13)
            sprints.append(
                {
                    "index": index,
                    "number": index + 1,
                    "start_date": start,
                    "end_date": end,
                    "events": [
                        {
                            "id": event.id,
                            "name": event.name,
                            "event_date": event.event_date,
                            "end_date": event.event_end_date,
                            "event_type": event.event_type,
                        }
                        for event in sorted_events
                        if event.event_date <= end
                        and (event.event_end_date or event.event_date) >= start
                    ],
                }
            )
    return ProgramBoardRead(
        initialized=cycle.program_board_initialized,
        version=cycle.version,
        cycle_id=cycle.id,
        cycle_status=cycle.status,
        sprints=sprints,
        tribes=tribe_rows,
        teams=team_rows,
        cards=cards,
        connections=rows,
        conflicts=conflicts,
    )


async def replace_program_board(
    session: AsyncSession,
    cycle: PiCycle,
    payload: ProgramBoardWrite,
) -> ProgramBoardRead:
    client_uids = [row.client_uid.strip().casefold() for row in payload.connections]
    if len(client_uids) != len(set(client_uids)):
        raise ValueError("UID связи должен быть уникален в пределах PI-цикла")

    initiatives_by_ref, _, stories_by_ref, _, work_items_by_ref, _ = await _endpoint_maps(session, cycle.id)

    def resolve(kind: str, ref: str) -> tuple[str, uuid.UUID]:
        normalized_ref = ref.strip().casefold()
        if kind == "c":
            initiative = initiatives_by_ref.get(normalized_ref)
            if initiative is None:
                raise ValueError(f"Инициатива как точка связи не найдена в данном PI-цикле: {ref}")
            return "initiative", initiative.id
        if kind == "g":
            story = stories_by_ref.get(normalized_ref)
            if story is None:
                raise ValueError(f"Story endpoint was not found in this PI cycle: {ref}")
            return "story", story.id
        item = work_items_by_ref.get(normalized_ref)
        if item is None:
            raise ValueError(f"Задача как точка связи не найдена в данном PI-цикле: {ref}")
        return "work_item", item.id

    resolved = []
    edge_keys: set[tuple[str, uuid.UUID, str, uuid.UUID]] = set()
    for source in payload.connections:
        source_kind, source_id = resolve(source.source.kind, source.source.ref)
        target_kind, target_id = resolve(source.target.kind, source.target.ref)
        if source_kind == target_kind and source_id == target_id:
            raise ValueError("Связь не может указывать сама на себя")
        edge_key = (source_kind, source_id, target_kind, target_id)
        if edge_key in edge_keys:
            raise ValueError("Одинаковая направленная связь может существовать только один раз")
        edge_keys.add(edge_key)
        resolved.append((source, source_kind, source_id, target_kind, target_id))

    existing = list(
        (
            await session.scalars(
                select(BoardConnection).where(BoardConnection.cycle_id == cycle.id)
            )
        ).all()
    )
    existing_by_id = {row.id: row for row in existing}
    existing_by_uid = {row.client_uid.casefold(): row for row in existing}
    desired_ids: set[uuid.UUID] = set()

    for position, (source, source_kind, source_id, target_kind, target_id) in enumerate(resolved):
        uid = source.client_uid.strip()
        connection = existing_by_id.get(source.id) if source.id else None
        uid_match = existing_by_uid.get(uid.casefold())
        if source.id is not None and connection is None:
            raise ValueError(
                f"ID связи не найден в данном PI-цикле: {source.id}"
            )
        if connection is not None and uid_match is not None and connection.id != uid_match.id:
            raise ValueError(f"ID связи не соответствует клиентскому UID: {uid}")
        if connection is None:
            connection = uid_match
        if connection is None:
            connection = BoardConnection(
                id=uuid.uuid4(),
                cycle_id=cycle.id,
                client_uid=uid,
                source_kind=source_kind,
                source_id=source_id,
                target_kind=target_kind,
                target_id=target_id,
            )
            session.add(connection)
        connection.client_uid = uid
        connection.source_kind = source_kind
        connection.source_id = source_id
        connection.target_kind = target_kind
        connection.target_id = target_id
        connection.relation_type = source.relation_type.strip() or "depends_on"
        connection.bend_dx = float(source.bend.dx) if source.bend else None
        connection.bend_dy = float(source.bend.dy) if source.bend else None
        connection.sort_order = source.sort_order if source.sort_order is not None else position
        desired_ids.add(connection.id)

    for connection in existing:
        if connection.id not in desired_ids:
            await session.delete(connection)
    cycle.program_board_initialized = True
    await session.commit()
    return await read_program_board(session, cycle)


async def delete_dangling_connections(
    session: AsyncSession,
    cycle_id: uuid.UUID,
) -> None:
    await session.flush()
    _, initiatives, _, stories, _, work_items = await _endpoint_maps(session, cycle_id)
    valid_initiatives = set(initiatives)
    valid_stories = set(stories)
    valid_work_items = set(work_items)
    connections = (
        await session.scalars(
            select(BoardConnection).where(BoardConnection.cycle_id == cycle_id)
        )
    ).all()
    for connection in connections:
        source_valid = (
            connection.source_id in valid_initiatives
            if connection.source_kind in {"initiative", "c"}
            else (
                connection.source_id in valid_stories
                if connection.source_kind in {"story", "g"}
                else connection.source_id in valid_work_items
            )
        )
        target_valid = (
            connection.target_id in valid_initiatives
            if connection.target_kind in {"initiative", "c"}
            else (
                connection.target_id in valid_stories
                if connection.target_kind in {"story", "g"}
                else connection.target_id in valid_work_items
            )
        )
        if not source_valid or not target_valid:
            await session.delete(connection)


async def _initiative_with_executors(
    session: AsyncSession, cycle: PiCycle, initiative_id: uuid.UUID
) -> Initiative:
    initiative = await session.scalar(
        select(Initiative)
        .execution_options(populate_existing=True)
        .options(
            selectinload(Initiative.executors),
            selectinload(Initiative.stories),
            selectinload(Initiative.work_items),
        )
        .where(Initiative.cycle_id == cycle.id, Initiative.id == initiative_id)
    )
    if initiative is None:
        raise ValueError("Инициатива не найдена в данном PI-цикле")
    if not initiative.on_board:
        raise ValueError("Инициатива не опубликована на командные доски")
    return initiative


def _primary_team_id(initiative: Initiative) -> uuid.UUID | None:
    primary = min(
        initiative.executors,
        key=lambda row: (row.sort_order, str(row.id)),
        default=None,
    )
    return primary.team_id if primary else None


def _period_after_parent(
    sprint_index: int | None,
    week_index: int | None,
    parent_sprint_index: int | None,
    parent_week_index: int | None,
) -> bool:
    if sprint_index is None or parent_sprint_index is None:
        return False
    if sprint_index != parent_sprint_index:
        return sprint_index > parent_sprint_index
    if week_index is None or parent_week_index is None:
        return False
    return week_index > parent_week_index


def _validate_initiative_children_period(
    initiative: Initiative,
    sprint_index: int | None,
    week_index: int | None,
) -> None:
    for story in initiative.stories:
        if _period_after_parent(story.sprint_index, story.week_index, sprint_index, week_index):
            raise ValueError("Главная задача не может быть запланирована раньше своих историй")
    for item in initiative.work_items:
        if _period_after_parent(item.sprint_index, item.week_index, sprint_index, week_index):
            raise ValueError("Главная задача не может быть запланирована раньше своих подзадач")


async def move_program_board_initiative(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    payload: ProgramBoardMoveCommand,
) -> ProgramBoardRead:
    initiative = await _initiative_with_executors(session, cycle, initiative_id)
    validate_sprint_position(cycle, payload.sprint_index, None, f"Инициатива {initiative.issue_key}")
    _validate_initiative_children_period(initiative, payload.sprint_index, None)
    primary_team_id = _primary_team_id(initiative)
    if primary_team_id is None:
        raise ValueError("У инициативы нет команды-исполнителя")
    active_team = await session.scalar(
        select(PiCycleTeam.id).where(
            PiCycleTeam.cycle_id == cycle.id,
            PiCycleTeam.team_id == primary_team_id,
        )
    )
    if active_team is None:
        raise ValueError("Команда-исполнитель инициативы не входит в данный PI-цикл")

    lane_candidates = list(
        (
            await session.scalars(
                select(Initiative)
                .options(selectinload(Initiative.executors))
                .where(
                    Initiative.cycle_id == cycle.id,
                    Initiative.on_board.is_(True),
                    Initiative.id != initiative.id,
                    Initiative.sprint_index == payload.sprint_index,
                )
                .order_by(Initiative.board_sort_order, Initiative.created_at, Initiative.id)
            )
        ).all()
    )
    lane = [row for row in lane_candidates if _primary_team_id(row) == primary_team_id]
    insert_at = min(payload.sort_order, len(lane))
    lane.insert(insert_at, initiative)
    for position, row in enumerate(lane):
        row.board_sort_order = position
    if initiative.sprint_index != payload.sprint_index:
        initiative.agreed = False
    initiative.sprint_index = payload.sprint_index
    initiative.week_index = None
    cycle.boards_initialized = True
    cycle.program_board_initialized = True
    await session.commit()
    return await read_program_board(session, cycle)


async def _resolve_endpoint_id(
    session: AsyncSession,
    cycle: PiCycle,
    endpoint,
) -> tuple[str, uuid.UUID]:
    if endpoint.kind == "initiative":
        initiative = await session.scalar(
            select(Initiative).where(
                Initiative.id == endpoint.id,
                Initiative.cycle_id == cycle.id,
                Initiative.on_board.is_(True),
            )
        )
        if initiative is None:
            raise ValueError("Инициатива как точка связи отсутствует на активных досках PI")
        return "initiative", initiative.id
    if endpoint.kind == "story":
        story = await session.scalar(
            select(Story)
            .join(Initiative, Initiative.id == Story.initiative_id)
            .where(
                Story.id == endpoint.id,
                Initiative.cycle_id == cycle.id,
                Initiative.on_board.is_(True),
            )
        )
        if story is None:
            raise ValueError("Story endpoint is absent from active PI team boards")
        return "story", story.id
    item = await session.scalar(
        select(WorkItem)
        .join(Initiative, Initiative.id == WorkItem.initiative_id)
        .where(
            WorkItem.id == endpoint.id,
            Initiative.cycle_id == cycle.id,
            Initiative.on_board.is_(True),
        )
    )
    if item is None:
        raise ValueError("Задача как точка связи отсутствует на активных досках PI")
    return "work_item", item.id


async def _assert_edge_available(
    session: AsyncSession,
    cycle: PiCycle,
    source_kind: str,
    source_id: uuid.UUID,
    target_kind: str,
    target_id: uuid.UUID,
    *,
    current_id: uuid.UUID | None = None,
) -> None:
    if source_kind == target_kind and source_id == target_id:
        raise ValueError("Связь не может указывать сама на себя")
    statement = select(BoardConnection.id).where(
        BoardConnection.cycle_id == cycle.id,
        BoardConnection.source_kind == source_kind,
        BoardConnection.source_id == source_id,
        BoardConnection.target_kind == target_kind,
        BoardConnection.target_id == target_id,
    )
    if current_id is not None:
        statement = statement.where(BoardConnection.id != current_id)
    if await session.scalar(statement):
        raise ValueError("Одинаковая направленная связь может существовать только один раз")


async def create_program_board_connection(
    session: AsyncSession,
    cycle: PiCycle,
    payload: ProgramBoardConnectionCreate,
) -> ProgramBoardRead:
    source_kind, source_id = await _resolve_endpoint_id(session, cycle, payload.source)
    target_kind, target_id = await _resolve_endpoint_id(session, cycle, payload.target)
    await _assert_edge_available(
        session, cycle, source_kind, source_id, target_kind, target_id
    )
    connection_id = uuid.uuid4()
    max_order = await session.scalar(
        select(func.max(BoardConnection.sort_order)).where(
            BoardConnection.cycle_id == cycle.id
        )
    )
    session.add(
        BoardConnection(
            id=connection_id,
            cycle_id=cycle.id,
            client_uid=str(connection_id),
            source_kind=source_kind,
            source_id=source_id,
            target_kind=target_kind,
            target_id=target_id,
            relation_type=payload.relation_type.strip(),
            bend_dx=float(payload.bend.dx) if payload.bend else None,
            bend_dy=float(payload.bend.dy) if payload.bend else None,
            sort_order=(int(max_order) + 1) if max_order is not None else 0,
        )
    )
    cycle.program_board_initialized = True
    await session.commit()
    return await read_program_board(session, cycle)


async def _connection_for_command(
    session: AsyncSession, cycle: PiCycle, connection_id: uuid.UUID
) -> BoardConnection:
    connection = await session.scalar(
        select(BoardConnection).where(
            BoardConnection.cycle_id == cycle.id,
            BoardConnection.id == connection_id,
        )
    )
    if connection is None:
        raise ValueError("Связь не найдена в данном PI-цикле")
    return connection


async def update_program_board_connection(
    session: AsyncSession,
    cycle: PiCycle,
    connection_id: uuid.UUID,
    payload: ProgramBoardConnectionUpdate,
) -> ProgramBoardRead:
    connection = await _connection_for_command(session, cycle, connection_id)
    source_kind, source_id = connection.source_kind, connection.source_id
    target_kind, target_id = connection.target_kind, connection.target_id
    if payload.source is not None:
        source_kind, source_id = await _resolve_endpoint_id(session, cycle, payload.source)
    if payload.target is not None:
        target_kind, target_id = await _resolve_endpoint_id(session, cycle, payload.target)
    await _assert_edge_available(
        session,
        cycle,
        source_kind,
        source_id,
        target_kind,
        target_id,
        current_id=connection.id,
    )
    connection.source_kind = source_kind
    connection.source_id = source_id
    connection.target_kind = target_kind
    connection.target_id = target_id
    if payload.relation_type is not None:
        connection.relation_type = payload.relation_type.strip()
    if payload.clear_bend:
        connection.bend_dx = None
        connection.bend_dy = None
    elif payload.bend is not None:
        connection.bend_dx = float(payload.bend.dx)
        connection.bend_dy = float(payload.bend.dy)
    await session.commit()
    return await read_program_board(session, cycle)


async def delete_program_board_connection(
    session: AsyncSession,
    cycle: PiCycle,
    connection_id: uuid.UUID,
) -> ProgramBoardRead:
    connection = await _connection_for_command(session, cycle, connection_id)
    await session.delete(connection)
    await session.commit()
    return await read_program_board(session, cycle)
