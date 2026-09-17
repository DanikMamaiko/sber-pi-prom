"""Create, inspect, and remove an isolated Program Board load fixture."""

from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal, engine
from app.models.pi_cycle import (
    BoardConnection,
    Initiative,
    InitiativeExecutor,
    PiCycle,
    PiCycleTeam,
    PiGoal,
    Risk,
    Story,
    Team,
    Tribe,
    WorkItem,
)


DEFAULT_YEAR = 2099
DEFAULT_QUARTER = "Q4"
DEFAULT_RUN_ID = "VDI-2000"
DEFAULT_COUNT = 2_000
DEFAULT_TEAM_COUNT = 20
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,23}$")


@dataclass(frozen=True)
class FixtureScope:
    year: int
    quarter: str
    run_id: str

    @property
    def issue_prefix(self) -> str:
        return f"LOAD-{self.run_id.upper().replace('_', '-')}-"

    @property
    def tribe_name(self) -> str:
        return f"Нагрузочный тест {self.run_id}"

    def team_name(self, number: int) -> str:
        return f"Нагрузка {self.run_id} {number:02d}"

    @property
    def start_date(self) -> date:
        quarter_number = int(self.quarter[1])
        return date(self.year, (quarter_number - 1) * 3 + 1, 1)


@dataclass(frozen=True)
class FixtureStatus:
    cycle_id: str | None
    cards: int
    teams: int


def fixture_scope(args: argparse.Namespace) -> FixtureScope:
    run_id = args.run_id.strip()
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "--run-id: 1-24 символа; разрешены латинские буквы, цифры, '-' и '_'"
        )
    return FixtureScope(args.year, args.quarter.upper(), run_id.upper())


async def fixture_status(scope: FixtureScope) -> FixtureStatus:
    async with SessionLocal() as session:
        cycle = await session.scalar(
            select(PiCycle).where(
                PiCycle.year == scope.year,
                PiCycle.quarter == scope.quarter,
            )
        )
        tribe = await session.scalar(select(Tribe).where(Tribe.name == scope.tribe_name))
        cards = 0
        if cycle is not None:
            cards = int(
                await session.scalar(
                    select(func.count(Initiative.id)).where(
                        Initiative.cycle_id == cycle.id,
                        Initiative.issue_key.like(f"{scope.issue_prefix}%"),
                    )
                )
                or 0
            )
        teams = 0
        if tribe is not None:
            teams = int(
                await session.scalar(
                    select(func.count(Team.id)).where(Team.tribe_id == tribe.id)
                )
                or 0
            )
        return FixtureStatus(str(cycle.id) if cycle else None, cards, teams)


async def create_fixture(
    scope: FixtureScope,
    *,
    count: int,
    team_count: int,
    allow_existing_cycle: bool,
) -> tuple[int, FixtureStatus]:
    async with SessionLocal() as session:
        async with session.begin():
            cycle = await session.scalar(
                select(PiCycle).where(
                    PiCycle.year == scope.year,
                    PiCycle.quarter == scope.quarter,
                )
            )
            tribe = await session.scalar(
                select(Tribe).where(Tribe.name == scope.tribe_name)
            )
            scope_is_attached = False
            if cycle is not None and tribe is not None:
                scope_is_attached = bool(
                    await session.scalar(
                        select(PiCycleTeam.id)
                        .join(Team, Team.id == PiCycleTeam.team_id)
                        .where(
                            PiCycleTeam.cycle_id == cycle.id,
                            Team.tribe_id == tribe.id,
                        )
                    )
                )
            if cycle is not None and not scope_is_attached and not allow_existing_cycle:
                raise ValueError(
                    f"PI {scope.year} {scope.quarter} уже существует и не принадлежит "
                    "этому тестовому набору. Используйте другой PI или явно добавьте "
                    "--allow-existing-cycle."
                )
            if cycle is None:
                cycle = PiCycle(
                    year=scope.year,
                    quarter=scope.quarter,
                    start_date=scope.start_date,
                    sprint_count=6,
                    status="draft",
                )
                session.add(cycle)
                await session.flush()
            elif cycle.start_date is None:
                cycle.start_date = scope.start_date

            if tribe is None:
                tribe = Tribe(name=scope.tribe_name)
                session.add(tribe)
                await session.flush()

            team_names = [scope.team_name(number) for number in range(1, team_count + 1)]
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
            for name in team_names:
                if name not in teams_by_name:
                    team = Team(tribe_id=tribe.id, name=name, team_type="Agile")
                    session.add(team)
                    teams_by_name[name] = team
            await session.flush()
            teams = [teams_by_name[name] for name in team_names]

            active_team_ids = set(
                (
                    await session.scalars(
                        select(PiCycleTeam.team_id).where(PiCycleTeam.cycle_id == cycle.id)
                    )
                ).all()
            )
            max_team_order = await session.scalar(
                select(func.max(PiCycleTeam.sort_order)).where(
                    PiCycleTeam.cycle_id == cycle.id
                )
            )
            next_team_order = (-1 if max_team_order is None else int(max_team_order)) + 1
            for team in teams:
                if team.id not in active_team_ids:
                    session.add(
                        PiCycleTeam(
                            cycle_id=cycle.id,
                            team_id=team.id,
                            team_type="Agile",
                            sort_order=next_team_order,
                        )
                    )
                    next_team_order += 1

            desired_keys = [
                f"{scope.issue_prefix}{number:06d}" for number in range(1, count + 1)
            ]
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
                select(func.max(Initiative.sort_order)).where(
                    Initiative.cycle_id == cycle.id
                )
            )
            next_initiative_order = (
                -1 if max_initiative_order is None else int(max_initiative_order)
            ) + 1
            sprint_count = max(1, int(cycle.sprint_count or 0))
            created_cards = 0

            for index, issue_key in enumerate(desired_keys):
                if issue_key in existing_keys:
                    continue
                primary_team_index = index % team_count
                primary_team = teams[primary_team_index]
                is_attraction = index % 4 in {1, 2}
                owner_team = (
                    teams[(primary_team_index + 1) % team_count]
                    if is_attraction
                    else primary_team
                )
                initiative = Initiative(
                    cycle_id=cycle.id,
                    issue_key=issue_key,
                    title=f"Нагрузочный стикер {scope.run_id} #{index + 1}",
                    description=(
                        "Автоматически создан для проверки Program Board на большом объёме."
                    ),
                    product="Program Board load test",
                    owner_team_id=owner_team.id,
                    initiative_type="Нагрузочный тест",
                    status="on_board",
                    pre_planned=True,
                    on_board=True,
                    agreed=index % 4 == 2,
                    tags=["load-test", scope.run_id, f"wave-{index % 10 + 1}"],
                    sprint_index=(index // team_count) % sprint_count,
                    sort_order=next_initiative_order + index,
                    board_sort_order=index // (team_count * sprint_count),
                )
                initiative.executors.append(
                    InitiativeExecutor(
                        team_id=primary_team.id,
                        effort_by_competency={
                            "DEV": float(index % 8 + 1),
                            "QA": float(index % 3 + 1),
                        },
                        sort_order=0,
                    )
                )
                if index % 10 == 0:
                    initiative.executors.append(
                        InitiativeExecutor(
                            team_id=teams[(primary_team_index + 2) % team_count].id,
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
            if created_cards:
                cycle.version = int(cycle.version or 0) + 1

    return created_cards, await fixture_status(scope)


async def cleanup_fixture(scope: FixtureScope) -> tuple[int, FixtureStatus]:
    deleted_cards = 0
    async with SessionLocal() as session:
        async with session.begin():
            cycle = await session.scalar(
                select(PiCycle).where(
                    PiCycle.year == scope.year,
                    PiCycle.quarter == scope.quarter,
                )
            )
            if cycle is None:
                return deleted_cards, FixtureStatus(None, 0, 0)

            initiative_ids = list(
                (
                    await session.scalars(
                        select(Initiative.id).where(
                            Initiative.cycle_id == cycle.id,
                            Initiative.issue_key.like(f"{scope.issue_prefix}%"),
                        )
                    )
                ).all()
            )
            if initiative_ids:
                story_ids = list(
                    (
                        await session.scalars(
                            select(Story.id).where(Story.initiative_id.in_(initiative_ids))
                        )
                    ).all()
                )
                work_item_ids = list(
                    (
                        await session.scalars(
                            select(WorkItem.id).where(
                                WorkItem.initiative_id.in_(initiative_ids)
                            )
                        )
                    ).all()
                )
                endpoint_ids = initiative_ids + story_ids + work_item_ids
                # Board connection endpoints are polymorphic UUIDs and intentionally
                # have no foreign keys, so remove matching edges before the cards.
                await session.execute(
                    delete(BoardConnection).where(
                        BoardConnection.cycle_id == cycle.id,
                        or_(
                            BoardConnection.source_id.in_(endpoint_ids),
                            BoardConnection.target_id.in_(endpoint_ids),
                        ),
                    )
                )
                # These optional references have foreign keys without ON DELETE SET NULL.
                await session.execute(
                    update(PiGoal)
                    .where(PiGoal.initiative_id.in_(initiative_ids))
                    .values(initiative_id=None)
                )
                await session.execute(
                    update(Risk)
                    .where(Risk.initiative_id.in_(initiative_ids))
                    .values(initiative_id=None)
                )
                result = await session.execute(
                    delete(Initiative).where(Initiative.id.in_(initiative_ids))
                )
                deleted_cards = int(result.rowcount or 0)
                if deleted_cards:
                    cycle.version = int(cycle.version or 0) + 1

    return deleted_cards, await fixture_status(scope)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "status", "cleanup"))
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument(
        "--quarter", choices=("Q1", "Q2", "Q3", "Q4"), default=DEFAULT_QUARTER
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--teams", type=int, default=DEFAULT_TEAM_COUNT)
    parser.add_argument(
        "--allow-existing-cycle",
        action="store_true",
        help="Разрешить добавление набора в PI, который не был создан этим run-id",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Подтвердить удаление для action=cleanup",
    )
    return parser


async def async_main(args: argparse.Namespace) -> int:
    try:
        scope = fixture_scope(args)
        if args.year < 2000 or args.year > 9999:
            raise ValueError("--year должен быть в диапазоне от 2000 до 9999")
        if args.count < 1 or args.count > 100_000:
            raise ValueError("--count должен быть в диапазоне от 1 до 100000")
        if args.teams < 1 or args.teams > 200:
            raise ValueError("--teams должен быть в диапазоне от 1 до 200")

        if args.action == "status":
            status = await fixture_status(scope)
            print(
                f"PI {scope.year} {scope.quarter}; run-id={scope.run_id}; "
                f"cycle_id={status.cycle_id or '-'}; стикеров={status.cards}; "
                f"тестовых команд={status.teams}."
            )
            return 0
        if args.action == "create":
            created, status = await create_fixture(
                scope,
                count=args.count,
                team_count=args.teams,
                allow_existing_cycle=args.allow_existing_cycle,
            )
            print(
                f"PI {scope.year} {scope.quarter}; run-id={scope.run_id}; "
                f"создано={created}; всего тестовых стикеров={status.cards}; "
                f"cycle_id={status.cycle_id}."
            )
            return 0
        if not args.yes:
            raise ValueError("cleanup требует явного подтверждения --yes")
        deleted, status = await cleanup_fixture(scope)
        print(
            f"PI {scope.year} {scope.quarter}; run-id={scope.run_id}; "
            f"удалено={deleted}; осталось тестовых стикеров={status.cards}. "
            "Тестовый PI и справочные команды сохранены."
        )
        return 0
    except (SQLAlchemyError, OSError, ValueError) as error:
        print(f"Ошибка: {error}")
        return 1
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
