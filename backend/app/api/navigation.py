from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission
from app.auth.models import CurrentUser
from app.auth.permissions import Permission
from app.db.session import get_session
from app.models.pi_cycle import PiCycle
from app.schemas.auth import (
    NavigationCycleCreate,
    NavigationCycleRead,
    NavigationRead,
    NavigationSectionRead,
    NavigationTabRead,
)


router = APIRouter(prefix="/app", tags=["App"])

TAB_DEFINITIONS = (
    ("data", "Данные PI-цикла", Permission.PI_DATA_READ, Permission.PI_DATA_WRITE, None),
    ("backlog", "Бэклог команд", Permission.BACKLOG_READ, Permission.BACKLOG_WRITE, None),
    ("prep", "Pre PI Planning", Permission.PRE_PI_READ, Permission.PRE_PI_WRITE, None),
    ("goals", "Цели", Permission.GOALS_READ, Permission.GOALS_WRITE, None),
    (
        "teams",
        "Командные доски",
        Permission.TEAM_BOARDS_READ,
        Permission.TEAM_BOARDS_WRITE,
        Permission.TASKS_APPROVE,
    ),
    (
        "pb",
        "Program Board",
        Permission.PROGRAM_BOARD_READ,
        Permission.PROGRAM_BOARD_WRITE,
        None,
    ),
    ("risks", "Риски", Permission.RISKS_READ, Permission.RISKS_WRITE, None),
)


@router.post("/pi-cycles", response_model=NavigationCycleRead)
async def select_pi_cycle(
    payload: NavigationCycleCreate,
    _user: CurrentUser = Depends(require_permission(Permission.PI_CYCLE_SELECT)),
    session: AsyncSession = Depends(get_session),
) -> NavigationCycleRead:
    cycle = await session.scalar(
        select(PiCycle).where(PiCycle.year == payload.year, PiCycle.quarter == payload.quarter)
    )
    if cycle is None:
        cycle = PiCycle(
            year=payload.year,
            quarter=payload.quarter,
            sprint_count=6,
            setup_initialized=True,
        )
        session.add(cycle)
        try:
            await session.commit()
        except IntegrityError:
            # Одновременный первый вход в один квартал остаётся идемпотентным.
            await session.rollback()
            cycle = await session.scalar(
                select(PiCycle).where(
                    PiCycle.year == payload.year,
                    PiCycle.quarter == payload.quarter,
                )
            )
        else:
            await session.refresh(cycle)
    return NavigationCycleRead(id=cycle.id, year=cycle.year, quarter=cycle.quarter)


@router.get("/navigation", response_model=NavigationRead)
async def navigation(
    user: CurrentUser = Depends(require_permission(Permission.APP_NAVIGATE)),
    session: AsyncSession = Depends(get_session),
) -> NavigationRead:
    cycles = (
        await session.scalars(select(PiCycle).order_by(PiCycle.year, PiCycle.quarter))
    ).all()
    tabs = [
        NavigationTabRead(
            id=tab_id,
            name=name,
            can_write=write_permission in user.permissions,
            can_approve=bool(approve_permission and approve_permission in user.permissions),
        )
        for tab_id, name, read_permission, write_permission, approve_permission in TAB_DEFINITIONS
        if read_permission in user.permissions
    ]
    return NavigationRead(
        sections=[
            NavigationSectionRead(
                id="budget",
                name="Бюджетирование",
                enabled=False,
                status="development",
                message="Находится в разработке. Будет доступно позже.",
            ),
            NavigationSectionRead(id="pi_cycle", name="PI-цикл", enabled=True),
        ],
        tabs=tabs,
        pi_cycles=[
            NavigationCycleRead(id=cycle.id, year=cycle.year, quarter=cycle.quarter)
            for cycle in cycles
        ],
    )
