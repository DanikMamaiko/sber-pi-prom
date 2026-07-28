import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.db.session import get_session
from app.models.pi_cycle import PiCycleTeam, Risk
from app.schemas.pi_cycle import (
    RiskCreate,
    RiskCreateCommand,
    RiskDeleteCommand,
    RiskLinkCommand,
    RiskRead,
    RiskReorderCommand,
    RiskRoamCommand,
    RiskStatusCommand,
    RiskUpdateCommand,
    RisksRead,
    RisksWrite,
)
from app.services.optimistic_locking import lock_cycle
from app.services.risks import (
    create_risk_command,
    delete_risk_command,
    read_risks,
    reorder_risks_command,
    replace_risks,
    update_risk_command,
    update_risk_link_command,
    update_risk_roam_command,
    update_risk_status_command,
)

router = APIRouter(tags=["PI Cycle"])


async def _run_risk_command(session: AsyncSession, operation):
    try:
        return await operation
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("/pi-cycles/{cycle_id}/risks", response_model=list[RiskRead])
async def list_risks(cycle_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    await get_cycle_or_404(session, cycle_id)
    result = await session.scalars(
        select(Risk).where(Risk.cycle_id == cycle_id).order_by(Risk.created_at.desc())
    )
    return result.all()


@router.get("/pi-cycles/{cycle_id}/risks-board", response_model=RisksRead)
async def get_risks_board(
    cycle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    cycle = await get_cycle_or_404(session, cycle_id)
    return await read_risks(session, cycle)


@router.put("/pi-cycles/{cycle_id}/risks-board", response_model=RisksRead)
async def put_risks_board(
    cycle_id: uuid.UUID,
    payload: RisksWrite,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    try:
        return await replace_risks(session, cycle, payload)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post(
    "/pi-cycles/{cycle_id}/risks-board/risks",
    response_model=RisksRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_risks_board_risk(
    cycle_id: uuid.UUID,
    payload: RiskCreateCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_risk_command(session, create_risk_command(session, cycle, payload))


@router.patch("/pi-cycles/{cycle_id}/risks-board/risks/{risk_id}", response_model=RisksRead)
async def patch_risks_board_risk(
    cycle_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: RiskUpdateCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_risk_command(session, update_risk_command(session, cycle, risk_id, payload))


@router.delete("/pi-cycles/{cycle_id}/risks-board/risks/{risk_id}", response_model=RisksRead)
async def delete_risks_board_risk(
    cycle_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: RiskDeleteCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_risk_command(session, delete_risk_command(session, cycle, risk_id, payload))


@router.put("/pi-cycles/{cycle_id}/risks-board/order", response_model=RisksRead)
async def put_risks_board_order(
    cycle_id: uuid.UUID,
    payload: RiskReorderCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_risk_command(session, reorder_risks_command(session, cycle, payload))


@router.patch(
    "/pi-cycles/{cycle_id}/risks-board/risks/{risk_id}/status",
    response_model=RisksRead,
)
async def patch_risks_board_risk_status(
    cycle_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: RiskStatusCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_risk_command(
        session,
        update_risk_status_command(session, cycle, risk_id, payload),
    )


@router.patch(
    "/pi-cycles/{cycle_id}/risks-board/risks/{risk_id}/roam",
    response_model=RisksRead,
)
async def patch_risks_board_risk_roam(
    cycle_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: RiskRoamCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_risk_command(
        session,
        update_risk_roam_command(session, cycle, risk_id, payload),
    )


@router.post(
    "/pi-cycles/{cycle_id}/risks-board/risks/{risk_id}/links",
    response_model=RisksRead,
)
async def post_risks_board_risk_link(
    cycle_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: RiskLinkCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    return await _run_risk_command(session, update_risk_link_command(session, cycle, risk_id, payload))


@router.delete(
    "/pi-cycles/{cycle_id}/risks-board/risks/{risk_id}/links",
    response_model=RisksRead,
)
async def delete_risks_board_risk_link(
    cycle_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: RiskDeleteCommand,
    session: AsyncSession = Depends(get_session),
):
    cycle = await lock_cycle(session, cycle_id, payload.expected_version)
    link_payload = RiskLinkCommand(expected_version=payload.expected_version, scope="general")
    return await _run_risk_command(
        session,
        update_risk_link_command(session, cycle, risk_id, link_payload),
    )


@router.post("/pi-cycles/{cycle_id}/risks", response_model=RiskRead, status_code=status.HTTP_201_CREATED)
async def create_risk(
    cycle_id: uuid.UUID,
    payload: RiskCreate,
    session: AsyncSession = Depends(get_session),
):
    await lock_cycle(session, cycle_id)
    if payload.scope == "general" and (payload.team_id is not None or payload.is_shared):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A general risk cannot reference a team or be shared",
        )
    if payload.scope == "team":
        if payload.team_id is None or not await session.scalar(
            select(PiCycleTeam).where(
                PiCycleTeam.cycle_id == cycle_id,
                PiCycleTeam.team_id == payload.team_id,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Risk team is not part of this PI cycle",
            )
    risk_id = uuid.uuid4()
    risk = Risk(
        id=risk_id,
        cycle_id=cycle_id,
        client_uid=f"risk-{risk_id}",
        **payload.model_dump(),
    )
    session.add(risk)
    await session.commit()
    await session.refresh(risk)
    return risk
