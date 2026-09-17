"""Create an idempotent 1,000-card Program Board load fixture for 2026 Q4."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.pi_cycle import (  # noqa: E402
    Initiative,
    InitiativeExecutor,
    PiCycle,
    PiCycleTeam,
    Team,
    Tribe,
)


YEAR = 2026
QUARTER = "Q4"
ISSUE_PREFIX = "LOAD-Q4-"
TRIBE_NAME = "Нагрузочный тест Q4 2026"
TEAM_COUNT = 20


async def seed(count: int) -> tuple[int, int, int]:
    async with SessionLocal() as session:
        async with session.begin():
            cycle = await session.scalar(
                select(PiCycle).where(PiCycle.year == YEAR, PiCycle.quarter == QUARTER)
            )
            if cycle is None:
                cycle = PiCycle(
                    year=YEAR,
                    quarter=QUARTER,
                    start_date=date(2026, 10, 1),
                    sprint_count=6,
                    status="draft",
                )
                session.add(cycle)
                await session.flush()
            elif cycle.start_date is None:
                cycle.start_date = date(2026, 10, 1)

            tribe = await session.scalar(select(Tribe).where(Tribe.name == TRIBE_NAME))
            if tribe is None:
                tribe = Tribe(name=TRIBE_NAME)
                session.add(tribe)
                await session.flush()

            team_names = [f"Нагрузка {number:02d}" for number in range(1, TEAM_COUNT + 1)]
            existing_teams = list(
                (
                    await session.scalars(
                        select(Team).where(
                            Team.tribe_id == tribe.id,
                            Team.name.in_(team_names),
                        )
                    )
                ).all()
            )
            teams_by_name = {team.name: team for team in existing_teams}
            created_teams = 0
            for name in team_names:
                if name not in teams_by_name:
                    team = Team(tribe_id=tribe.id, name=name, team_type="Agile")
                    session.add(team)
                    teams_by_name[name] = team
                    created_teams += 1
            await session.flush()
            teams = [teams_by_name[name] for name in team_names]

            active_team_ids = set(
                (
                    await session.scalars(
                        select(PiCycleTeam.team_id).where(PiCycleTeam.cycle_id == cycle.id)
                    )
                ).all()
            )
            max_cycle_team_order = await session.scalar(
                select(func.max(PiCycleTeam.sort_order)).where(PiCycleTeam.cycle_id == cycle.id)
            )
            next_cycle_team_order = (
                -1 if max_cycle_team_order is None else int(max_cycle_team_order)
            ) + 1
            created_cycle_teams = 0
            for team in teams:
                if team.id not in active_team_ids:
                    session.add(
                        PiCycleTeam(
                            cycle_id=cycle.id,
                            team_id=team.id,
                            team_type="Agile",
                            sort_order=next_cycle_team_order,
                        )
                    )
                    next_cycle_team_order += 1
                    created_cycle_teams += 1

            desired_keys = [f"{ISSUE_PREFIX}{number:04d}" for number in range(1, count + 1)]
            existing_keys = set(
                (
                    await session.scalars(
                        select(Initiative.issue_key).where(
                            Initiative.cycle_id == cycle.id,
                            Initiative.issue_key.in_(desired_keys),
                        )
                    )
                ).all()
            )
            max_initiative_order = await session.scalar(
                select(func.max(Initiative.sort_order)).where(Initiative.cycle_id == cycle.id)
            )
            next_initiative_order = (
                -1 if max_initiative_order is None else int(max_initiative_order)
            ) + 1
            sprint_count = max(1, int(cycle.sprint_count or 0))
            created_cards = 0

            for index, issue_key in enumerate(desired_keys):
                if issue_key in existing_keys:
                    continue
                primary_team_index = index % TEAM_COUNT
                primary_team = teams[primary_team_index]
                is_attraction = index % 4 in {1, 2}
                owner_team = teams[(primary_team_index + 1) % TEAM_COUNT] if is_attraction else primary_team
                sprint_index = (index // TEAM_COUNT) % sprint_count
                initiative = Initiative(
                    cycle_id=cycle.id,
                    issue_key=issue_key,
                    title=f"Нагрузочный стикер {index + 1}",
                    description="Автоматически создан для проверки Program Board на большом объёме.",
                    product="Program Board load test",
                    owner_team_id=owner_team.id,
                    initiative_type="Нагрузочный тест",
                    status="on_board",
                    pre_planned=True,
                    on_board=True,
                    agreed=index % 4 == 2,
                    tags=["load-test", f"wave-{index % 10 + 1}"],
                    sprint_index=sprint_index,
                    sort_order=next_initiative_order + index,
                    board_sort_order=index // (TEAM_COUNT * sprint_count),
                )
                initiative.executors.append(
                    InitiativeExecutor(
                        team_id=primary_team.id,
                        effort_by_competency={"DEV": float(index % 8 + 1), "QA": float(index % 3 + 1)},
                        sort_order=0,
                    )
                )
                if index % 10 == 0:
                    initiative.executors.append(
                        InitiativeExecutor(
                            team_id=teams[(primary_team_index + 2) % TEAM_COUNT].id,
                            effort_by_competency={"SA": 1.0},
                            sort_order=1,
                        )
                    )
                session.add(initiative)
                created_cards += 1

            cycle.setup_initialized = True
            cycle.initiatives_initialized = True
            cycle.boards_initialized = True
            cycle.program_board_initialized = True
            if created_cards or created_teams or created_cycle_teams:
                cycle.version = int(cycle.version or 0) + 1

        total_cards = await session.scalar(
            select(func.count(Initiative.id)).where(
                Initiative.cycle_id == cycle.id,
                Initiative.issue_key.like(f"{ISSUE_PREFIX}%"),
            )
        )
        return created_cards, int(total_cards or 0), created_teams


async def async_main(count: int) -> int:
    try:
        created_cards, total_cards, created_teams = await seed(count)
    except (SQLAlchemyError, OSError) as error:
        print(f"Не удалось подключиться к тестовой БД или записать данные: {type(error).__name__}")
        return 1
    finally:
        await engine.dispose()
    print(
        f"Q4 2026: создано стикеров {created_cards}, всего тестовых {total_cards}; "
        f"создано команд {created_teams}."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000, help="Количество тестовых стикеров")
    args = parser.parse_args()
    if args.count < 1 or args.count > 100_000:
        parser.error("--count должен быть в диапазоне от 1 до 100000")
    return asyncio.run(async_main(args.count))


if __name__ == "__main__":
    raise SystemExit(main())
