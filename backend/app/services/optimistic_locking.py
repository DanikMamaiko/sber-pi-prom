import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pi_cycle import BacklogBoardState, PiCycle


BACKLOG_STATE_ID = 1


def _conflict_detail(aggregate: str, expected: int, current: int) -> dict[str, object]:
    return {
        "message": "Aggregate was changed by another editor",
        "aggregate": aggregate,
        "expected_version": expected,
        "current_version": current,
    }


async def lock_cycle(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    expected_version: int | None = None,
) -> PiCycle:
    cycle = await session.scalar(
        select(PiCycle).where(PiCycle.id == cycle_id).with_for_update()
    )
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PI cycle not found")
    if expected_version is not None and cycle.version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_conflict_detail("pi_cycle", expected_version, cycle.version),
        )
    cycle.version += 1
    return cycle


async def lock_backlog(
    session: AsyncSession,
    expected_version: int | None = None,
) -> BacklogBoardState:
    marker = await session.scalar(
        select(BacklogBoardState)
        .where(BacklogBoardState.id == BACKLOG_STATE_ID)
        .with_for_update()
    )
    if marker is None:
        marker = BacklogBoardState(id=BACKLOG_STATE_ID, initialized=False, version=0)
        session.add(marker)
        await session.flush()
    if expected_version is not None and marker.version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_conflict_detail("backlog_board", expected_version, marker.version),
        )
    marker.version += 1
    return marker
