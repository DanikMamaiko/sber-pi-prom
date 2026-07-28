import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pi_cycle import PiCycle

router = APIRouter(tags=["PI Cycle"])


async def get_cycle_or_404(session: AsyncSession, cycle_id: uuid.UUID) -> PiCycle:
    cycle = await session.get(PiCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PI cycle not found")
    return cycle


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


