import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.db.session import get_session
from app.schemas.pi_cycle import (
    BacklogBoardRead,
    BacklogBoardWrite,
    BacklogDispatchWrite,
    BacklogItemCommand,
    BacklogItemDelete,
    BacklogReorderCommand,
)
from app.services.backlog_board import (
    BacklogCascadeRequired,
    BacklogNotFound,
    create_backlog_item,
    delete_backlog_item,
    dispatch_backlog_items,
    read_backlog_board,
    reorder_backlog_items,
    replace_backlog_board,
    update_backlog_item,
)
from app.services.optimistic_locking import lock_backlog

router = APIRouter(tags=["PI Cycle"])


async def _run_backlog_command(
    session: AsyncSession,
    operation,
    cycle_id: uuid.UUID | None = None,
):
    try:
        await operation
        await session.commit()
        return await read_backlog_board(session, cycle_id)
    except BacklogCascadeRequired as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.detail)
    except BacklogNotFound as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("/backlog-board", response_model=BacklogBoardRead)
async def get_backlog_board(
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    return await read_backlog_board(session, cycle_id)


@router.post(
    "/backlog-board/items",
    response_model=BacklogBoardRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_backlog_item(
    payload: BacklogItemCommand,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        create_backlog_item(session, payload, cycle_id),
        cycle_id,
    )


@router.patch("/backlog-board/items/{item_id}", response_model=BacklogBoardRead)
async def patch_backlog_item(
    item_id: uuid.UUID,
    payload: BacklogItemCommand,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        update_backlog_item(session, item_id, payload, cycle_id),
        cycle_id,
    )


@router.delete("/backlog-board/items/{item_id}", response_model=BacklogBoardRead)
async def delete_backlog_item_endpoint(
    item_id: uuid.UUID,
    payload: BacklogItemDelete,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        delete_backlog_item(session, item_id, payload),
        cycle_id,
    )


@router.put("/backlog-board/order", response_model=BacklogBoardRead)
async def put_backlog_order(
    payload: BacklogReorderCommand,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        reorder_backlog_items(session, payload),
        cycle_id,
    )


@router.put("/backlog-board", response_model=BacklogBoardRead)
async def put_backlog_board(
    payload: BacklogBoardWrite,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        replace_backlog_board(session, payload, cycle_id),
        cycle_id,
    )


@router.post("/backlog-board/dispatch", response_model=BacklogBoardRead)
async def dispatch_backlog(
    payload: BacklogDispatchWrite,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    return await _run_backlog_command(
        session,
        dispatch_backlog_items(session, payload),
        cycle_id,
    )


