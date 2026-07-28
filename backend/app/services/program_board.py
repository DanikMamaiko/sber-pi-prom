import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pi_cycle import BoardConnection, Initiative, PiCycle, WorkItem
from app.schemas.pi_cycle import (
    ProgramBoardConnectionRead,
    ProgramBoardRead,
    ProgramBoardWrite,
)


async def _endpoint_maps(
    session: AsyncSession,
    cycle_id: uuid.UUID,
) -> tuple[
    dict[str, Initiative],
    dict[uuid.UUID, Initiative],
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
    return (
        {row.issue_key.casefold(): row for row in initiatives},
        {row.id: row for row in initiatives},
        {row.client_uid.casefold(): row for row in work_items},
        {row.id: row for row in work_items},
    )


def _endpoint_ref(
    kind: str,
    endpoint_id: uuid.UUID,
    initiatives: dict[uuid.UUID, Initiative],
    work_items: dict[uuid.UUID, WorkItem],
) -> dict[str, str] | None:
    if kind in {"initiative", "c"}:
        initiative = initiatives.get(endpoint_id)
        return {"kind": "c", "ref": initiative.issue_key} if initiative else None
    if kind in {"work_item", "w"}:
        item = work_items.get(endpoint_id)
        return {"kind": "w", "ref": item.client_uid} if item else None
    return None


async def read_program_board(
    session: AsyncSession,
    cycle: PiCycle,
) -> ProgramBoardRead:
    _, initiatives, _, work_items = await _endpoint_maps(session, cycle.id)
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
    for connection in connections:
        source = _endpoint_ref(
            connection.source_kind,
            connection.source_id,
            initiatives,
            work_items,
        )
        target = _endpoint_ref(
            connection.target_kind,
            connection.target_id,
            initiatives,
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
    return ProgramBoardRead(
        initialized=cycle.program_board_initialized,
        version=cycle.version,
        connections=rows,
    )


async def replace_program_board(
    session: AsyncSession,
    cycle: PiCycle,
    payload: ProgramBoardWrite,
) -> ProgramBoardRead:
    client_uids = [row.client_uid.strip().casefold() for row in payload.connections]
    if len(client_uids) != len(set(client_uids)):
        raise ValueError("Connection UID must be unique inside a PI cycle")

    initiatives_by_ref, _, work_items_by_ref, _ = await _endpoint_maps(session, cycle.id)

    def resolve(kind: str, ref: str) -> tuple[str, uuid.UUID]:
        normalized_ref = ref.strip().casefold()
        if kind == "c":
            initiative = initiatives_by_ref.get(normalized_ref)
            if initiative is None:
                raise ValueError(f"Initiative endpoint is not found in this PI cycle: {ref}")
            return "initiative", initiative.id
        item = work_items_by_ref.get(normalized_ref)
        if item is None:
            raise ValueError(f"Work item endpoint is not found in this PI cycle: {ref}")
        return "work_item", item.id

    resolved = []
    edge_keys: set[tuple[str, uuid.UUID, str, uuid.UUID]] = set()
    for source in payload.connections:
        source_kind, source_id = resolve(source.source.kind, source.source.ref)
        target_kind, target_id = resolve(source.target.kind, source.target.ref)
        if source_kind == target_kind and source_id == target_id:
            raise ValueError("A connection cannot point to itself")
        edge_key = (source_kind, source_id, target_kind, target_id)
        if edge_key in edge_keys:
            raise ValueError("The same directed connection can only occur once")
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
                f"Connection ID is not found in this PI cycle: {source.id}"
            )
        if connection is not None and uid_match is not None and connection.id != uid_match.id:
            raise ValueError(f"Connection ID does not match client UID: {uid}")
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
    _, initiatives, _, work_items = await _endpoint_maps(session, cycle_id)
    valid_initiatives = set(initiatives)
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
            else connection.source_id in valid_work_items
        )
        target_valid = (
            connection.target_id in valid_initiatives
            if connection.target_kind in {"initiative", "c"}
            else connection.target_id in valid_work_items
        )
        if not source_valid or not target_valid:
            await session.delete(connection)
