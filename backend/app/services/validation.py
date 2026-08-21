import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import PiCycle, PiCycleTeam, Team


def normalize_name(value: str) -> str:
    return value.strip().casefold()


async def cycle_team_context(
    session: AsyncSession,
    cycle_id: uuid.UUID,
) -> tuple[
    dict[tuple[str, str], Team],
    dict[str, list[Team]],
    dict[uuid.UUID, set[str]],
]:
    rows = list(
        (
            await session.scalars(
                select(PiCycleTeam)
                .options(
                    selectinload(PiCycleTeam.team).selectinload(Team.tribe),
                    selectinload(PiCycleTeam.competencies),
                )
                .where(PiCycleTeam.cycle_id == cycle_id)
            )
        ).all()
    )
    by_key: dict[tuple[str, str], Team] = {}
    by_name: dict[str, list[Team]] = {}
    competencies: dict[uuid.UUID, set[str]] = {}
    for row in rows:
        team = row.team
        tribe_name = team.tribe.name if team.tribe else ""
        by_key[(normalize_name(tribe_name), normalize_name(team.name))] = team
        by_name.setdefault(normalize_name(team.name), []).append(team)
        competencies[team.id] = {
            value.code.strip().upper() for value in row.competencies if value.code.strip()
        }
    return by_key, by_name, competencies


def resolve_cycle_team(
    by_key: dict[tuple[str, str], Team],
    by_name: dict[str, list[Team]],
    tribe_name: str,
    team_name: str,
) -> Team:
    clean_team = team_name.strip()
    clean_tribe = tribe_name.strip()
    if not clean_team:
        raise ValueError("Укажите название команды")
    if clean_tribe:
        team = by_key.get((normalize_name(clean_tribe), normalize_name(clean_team)))
        if team is None:
            raise ValueError(
                f"Команда не входит в данный PI-цикл: {clean_tribe} / {clean_team}"
            )
        return team
    matches = by_name.get(normalize_name(clean_team), [])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"Имя команды неоднозначно среди трайбов: {clean_team}")
    raise ValueError(f"Команда не входит в данный PI-цикл: {clean_team}")


def validate_sprint_position(
    cycle: PiCycle,
    sprint_index: int | None,
    week_index: int | None,
    label: str,
) -> None:
    if sprint_index is None:
        if week_index is not None:
            raise ValueError(f"{label}: неделя не может быть указана без спринта")
        return
    if sprint_index < 0 or sprint_index >= cycle.sprint_count:
        raise ValueError(
            f"{label}: индекс спринта должен быть от 0 до {cycle.sprint_count - 1}"
        )
    if week_index not in {None, 0, 1}:
        raise ValueError(f"{label}: индекс недели должен быть 0 или 1")


def normalized_effort(
    values: dict[str, float],
    allowed_competencies: set[str] | None,
    label: str,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for raw_code, raw_value in values.items():
        code = str(raw_code).strip().upper()
        if not code:
            raise ValueError(f"{label}: код компетенции не может быть пустым")
        if code in result:
            raise ValueError(f"{label}: компетенция встречается более одного раза: {code}")
        if allowed_competencies is not None and code not in allowed_competencies:
            raise ValueError(f"{label}: компетенция не настроена для команды: {code}")
        value = float(raw_value)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{label}: трудоёмкость должна быть неотрицательным конечным числом")
        result[code] = value
    return result
