import uuid
from collections.abc import Iterable

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    Initiative,
    InitiativeAttraction,
    InitiativeExecutor,
    PiCycle,
    PiCycleGoalOption,
    PiCycleTeam,
    PiGoal,
    PiGoalInitiative,
    Team,
)
from app.schemas.pi_cycle import (
    PrePiDeleteCommand,
    PrePiInitiativeCommand,
    PrePiInitiativeRead,
    PrePiMoveCommand,
    PrePiRead,
    PrePiWrite,
)
from app.services.capacity import read_capacity
from app.services.program_board import delete_dangling_connections
from app.services.validation import (
    cycle_team_context,
    normalized_effort,
    resolve_cycle_team,
    validate_sprint_position,
)


DEV_FUNCTIONALITY_TYPE = "Развитие функционала"
TECH_COMMON_TYPE = "Общая тех. повестка"
TECH_TEAM_TYPE = "Командная тех. повестка"
REG_TYPE = "Требования законодательства"
# Команда-владелец, для которой регуляторка считается как «общая»; для остальных
# владельцев — как «командная». Сравнение по точному совпадению имени команды.
LEGAL_OWNER_TEAM = "Legal"
AGILE_REQUIRED_FIELDS = ["goal_text", "metric", "current_value", "target_value"]
IT_REQUIRED_FIELDS = ["goal_text"]
STATUS_TRANSITIONS = {
    "backlog": {"backlog", "planned"},
    "planned": {"backlog", "planned", "on_board"},
    "on_board": {"on_board", "done"},
    "done": {"done"},
}


class PrePiCascadeRequired(ValueError):
    def __init__(self, message: str, affected: list[dict[str, str]]):
        super().__init__(message)
        self.message = message
        self.affected = affected


def _clean_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = raw.strip()
        if value and value not in result:
            result.append(value)
    return result


def _effort_total(executor: InitiativeExecutor) -> float:
    return sum(float(value or 0) for value in (executor.effort_by_competency or {}).values())


def _regulatory_by_team(initiatives: Iterable[Initiative]) -> dict[str, dict[str, float]]:
    """Трудозатраты «Регуляторки» по командам-исполнителям с разбивкой на бакеты.

    Учитываются только запланированные (pre_planned) инициативы типа REG_TYPE. Бакет
    определяется командой-владельцем: Legal → «общая» (common), иная команда →
    «командная» (team). Усилие относится на исполнителей (как у техповестки — кто
    тратит capacity, на того и ложится), а не на владельца.
    """
    reg_by_team: dict[str, dict[str, float]] = {}
    for item in initiatives:
        if not item.pre_planned or item.initiative_type != REG_TYPE:
            continue
        owner_name = item.owner_team.name if item.owner_team else ""
        bucket = "common" if owner_name == LEGAL_OWNER_TEAM else "team"
        for executor in item.executors:
            target = reg_by_team.setdefault(executor.team.name, {"common": 0.0, "team": 0.0})
            target[bucket] += _effort_total(executor)
    return reg_by_team


def _is_it_project(team_type: str) -> bool:
    return team_type in {"ИТ-проект", "IT_PROJECT"}


def validate_status_transition(current: str, target: str) -> None:
    if target not in STATUS_TRANSITIONS.get(current, set()):
        raise ValueError(f"Недопустимый переход статуса инициативы: {current} -> {target}")


async def _cycle_teams(session: AsyncSession, cycle_id: uuid.UUID) -> list[PiCycleTeam]:
    return list(
        (
            await session.scalars(
                select(PiCycleTeam)
                .options(
                    selectinload(PiCycleTeam.team).selectinload(Team.tribe),
                    selectinload(PiCycleTeam.competencies),
                )
                .where(PiCycleTeam.cycle_id == cycle_id)
                .order_by(PiCycleTeam.sort_order, PiCycleTeam.id)
            )
        ).all()
    )


async def _initiatives_query(session: AsyncSession, cycle_id: uuid.UUID) -> list[Initiative]:
    return list(
        (
            await session.scalars(
                select(Initiative)
                .options(
                    selectinload(Initiative.owner_team).selectinload(Team.tribe),
                    selectinload(Initiative.executors)
                    .selectinload(InitiativeExecutor.team)
                    .selectinload(Team.tribe),
                    selectinload(Initiative.executors)
                    .selectinload(InitiativeExecutor.attraction_requests)
                    .selectinload(InitiativeAttraction.target_initiative),
                    selectinload(Initiative.executors)
                    .selectinload(InitiativeExecutor.attraction_requests)
                    .selectinload(InitiativeAttraction.target_team),
                    selectinload(Initiative.stories),
                    selectinload(Initiative.work_items),
                )
                .where(Initiative.cycle_id == cycle_id)
                .order_by(Initiative.pre_planned.desc(), Initiative.sort_order, Initiative.created_at, Initiative.id)
            )
        ).unique().all()
    )


def _required_fields(item: Initiative, team_type: str) -> list[str]:
    if item.initiative_type.strip() != DEV_FUNCTIONALITY_TYPE:
        return []
    return list(IT_REQUIRED_FIELDS if _is_it_project(team_type) else AGILE_REQUIRED_FIELDS)


def _attraction_read(row: InitiativeAttraction) -> dict:
    visual = {"pending": "purple", "approved": "red", "rejected": "gray"}.get(
        row.approval_status, "purple"
    )
    return {
        "id": row.id,
        "target_initiative_id": row.target_initiative_id,
        "issue_key": row.target_initiative.issue_key,
        "target_team_id": row.target_team_id,
        "team": row.target_team.name,
        "sprint_index": row.sprint_index,
        "approval_status": row.approval_status,
        "visual_state": visual,
        "sort_order": row.sort_order,
    }


def _initiative_read(item: Initiative, team_types: dict[uuid.UUID, str]) -> PrePiInitiativeRead:
    required = _required_fields(item, team_types.get(item.owner_team_id, "Agile"))
    actions = ["edit", "move", "reorder", "delete"]
    if item.pre_planned:
        actions.append("submit")
    return PrePiInitiativeRead(
        id=item.id,
        issue_key=item.issue_key,
        title=item.title,
        description=item.description or "",
        product=item.product or "",
        owner_team=item.owner_team.name if item.owner_team else "",
        owner_tribe=(item.owner_team.tribe.name if item.owner_team and item.owner_team.tribe else ""),
        initiative_type=item.initiative_type or "",
        status=item.status or "backlog",
        goal_text=item.goal_text or "",
        metric=item.metric or "",
        current_value=item.current_value or "",
        target_value=item.target_value or "",
        hypothesis=item.hypothesis or "",
        redesign=item.redesign or "",
        customer_priority=item.customer_priority or "",
        team_priority=item.team_priority or "",
        estimate=item.estimate or "",
        comment=item.comment or "",
        pre_planned=bool(item.pre_planned),
        on_board=bool(item.on_board),
        agreed=bool(item.agreed),
        tags=list(item.tags or []),
        sprint_index=item.sprint_index,
        week_index=item.week_index,
        sort_order=item.sort_order,
        total_estimate=sum(_effort_total(executor) for executor in item.executors),
        block="planned" if item.pre_planned else "backlog",
        required_fields=required,
        allowed_actions=actions,
        executors=[
            {
                "id": executor.id,
                "team_id": executor.team_id,
                "team": executor.team.name,
                "tribe": executor.team.tribe.name if executor.team.tribe else "",
                "effort_by_competency": dict(executor.effort_by_competency or {}),
                "attractions": [
                    _attraction_read(attraction)
                    for attraction in sorted(executor.attraction_requests, key=lambda value: value.sort_order)
                ],
                "sort_order": executor.sort_order,
            }
            for executor in sorted(item.executors, key=lambda value: value.sort_order)
        ],
    )


def _scope_metrics(
    team_rows: list[dict],
    tech_by_team: dict[str, dict[str, float]],
    reg_by_team: dict[str, dict[str, float]] | None = None,
) -> dict:
    available_by: dict[str, float] = {}
    planned_by: dict[str, float] = {}
    for row in team_rows:
        for code, value in row["available_by_competency"].items():
            available_by[code] = available_by.get(code, 0.0) + float(value or 0)
        for code, value in row["planned_by_competency"].items():
            planned_by[code] = planned_by.get(code, 0.0) + float(value or 0)
    competencies = {
        code: {
            "available": available_by.get(code, 0.0),
            "planned": planned_by.get(code, 0.0),
            "over_capacity": planned_by.get(code, 0.0) > available_by.get(code, 0.0),
        }
        for code in sorted(set(available_by) | set(planned_by))
    }
    calendar = sum(float(row["calendar_capacity"]) for row in team_rows)
    available = sum(float(row["available_capacity"]) for row in team_rows)
    planned = sum(float(row["planned_effort"]) for row in team_rows)
    tech_common = sum(tech_by_team.get(row["team"], {}).get("common", 0.0) for row in team_rows)
    tech_team = sum(tech_by_team.get(row["team"], {}).get("team", 0.0) for row in team_rows)
    tech_total = tech_common + tech_team
    reg_common = sum(reg_by_team.get(row["team"], {}).get("common", 0.0) for row in team_rows) if reg_by_team else 0.0
    reg_team = sum(reg_by_team.get(row["team"], {}).get("team", 0.0) for row in team_rows) if reg_by_team else 0.0
    reg_total = reg_common + reg_team
    return {
        "calendar_capacity": calendar,
        "available_capacity": available,
        "planned_capacity": planned,
        "remaining_capacity": available - planned,
        "over_capacity": planned > available,
        "competencies": competencies,
        "tech_agenda": {
            "total_effort": tech_total,
            "common_effort": tech_common,
            "team_effort": tech_team,
            "total_percent": round(tech_total / available * 100, 1) if available else None,
            "common_percent": round(tech_common / available * 100, 1) if available else None,
            "team_percent": round(tech_team / available * 100, 1) if available else None,
        },
        "reg_agenda": {
            "total_effort": reg_total,
            "common_effort": reg_common,
            "team_effort": reg_team,
            "total_percent": round(reg_total / available * 100, 1) if available else None,
            "common_percent": round(reg_common / available * 100, 1) if available else None,
            "team_percent": round(reg_team / available * 100, 1) if available else None,
        },
    }


async def read_pre_pi(session: AsyncSession, cycle: PiCycle) -> PrePiRead:
    initiatives = await _initiatives_query(session, cycle.id)
    cycle_teams = await _cycle_teams(session, cycle.id)
    team_types = {row.team_id: row.team_type or row.team.team_type for row in cycle_teams}
    rows = [_initiative_read(item, team_types) for item in initiatives]
    teams = [
        {
            "id": row.team.id,
            "cycle_team_id": row.id,
            "tribe_id": row.team.tribe_id,
            "tribe": row.team.tribe.name,
            "name": row.team.name,
            "team_type": row.team_type or row.team.team_type,
            "excluded_from_goals": row.excluded_from_goals,
            "competencies": [item.code for item in row.competencies],
            "sort_order": row.sort_order,
        }
        for row in cycle_teams
    ]
    tribes_by_id: dict[uuid.UUID, dict] = {}
    for team in teams:
        tribes_by_id.setdefault(team["tribe_id"], {"id": team["tribe_id"], "name": team["tribe"]})
    goal_options = list(
        (
            await session.scalars(
                select(PiCycleGoalOption)
                .where(PiCycleGoalOption.cycle_id == cycle.id)
                .order_by(PiCycleGoalOption.sort_order, PiCycleGoalOption.id)
            )
        ).all()
    )
    capacity_read = await read_capacity(session, cycle)
    capacity_teams = [row.model_dump(mode="json") for row in capacity_read.teams]
    tech_by_team: dict[str, dict[str, float]] = {}
    for item in initiatives:
        if not item.pre_planned:
            continue
        bucket = "common" if item.initiative_type == TECH_COMMON_TYPE else "team" if item.initiative_type == TECH_TEAM_TYPE else None
        if bucket is None:
            continue
        for executor in item.executors:
            target = tech_by_team.setdefault(executor.team.name, {"common": 0.0, "team": 0.0})
            target[bucket] += _effort_total(executor)
    reg_by_team = _regulatory_by_team(initiatives)
    team_metrics = {}
    for row in capacity_teams:
        team_ref = next(
            (value for value in teams if value["tribe"] == row["tribe"] and value["name"] == row["team"]),
            None,
        )
        if team_ref:
            team_metrics[str(team_ref["id"])] = _scope_metrics([row], tech_by_team, reg_by_team)
    tribe_metrics = {
        str(tribe["id"]): _scope_metrics(
            [row for row in capacity_teams if row["tribe"] == tribe["name"]], tech_by_team, reg_by_team
        )
        for tribe in tribes_by_id.values()
    }
    overall = _scope_metrics(capacity_teams, tech_by_team, reg_by_team)
    return PrePiRead(
        initialized=cycle.initiatives_initialized,
        version=cycle.version,
        cycle={
            "id": cycle.id,
            "year": cycle.year,
            "quarter": cycle.quarter,
            "start_date": cycle.start_date,
            "sprint_count": cycle.sprint_count,
        },
        tribes=list(tribes_by_id.values()),
        teams=teams,
        goal_options=[{"id": row.id, "name": row.name} for row in goal_options],
        initiatives=rows,
        planned=[row for row in rows if row.pre_planned],
        backlog=[row for row in rows if not row.pre_planned],
        capacity={"teams": team_metrics, "tribes": tribe_metrics, "overall": overall},
        tech_agenda=overall["tech_agenda"],
        reg_agenda=overall["reg_agenda"],
        allowed_values={
            "statuses": ["backlog", "planned", "on_board", "done"],
            "blocks": ["planned", "backlog"],
            "attraction_statuses": ["pending", "approved", "rejected"],
        },
    )


async def _initiative_or_error(session: AsyncSession, cycle_id: uuid.UUID, initiative_id: uuid.UUID) -> Initiative:
    rows = await _initiatives_query(session, cycle_id)
    item = next((row for row in rows if row.id == initiative_id), None)
    if item is None:
        raise ValueError("Инициатива не найдена в данном PI-цикле")
    return item


async def _replace_executors(
    session: AsyncSession,
    cycle: PiCycle,
    item: Initiative,
    sources,
) -> None:
    teams_by_key, teams_by_name, competencies_by_team = await cycle_team_context(session, cycle.id)
    initiatives = await _initiatives_query(session, cycle.id)
    initiatives_by_id = {row.id: row for row in initiatives}
    initiatives_by_key = {row.issue_key.casefold(): row for row in initiatives}
    existing_by_id = {row.id: row for row in item.executors}
    existing_by_team = {row.team_id: row for row in item.executors}
    used: set[uuid.UUID] = set()
    result: list[InitiativeExecutor] = []
    for position, source in enumerate(sources):
        team = None
        if source.team_id:
            team = next((value for value in teams_by_key.values() if value.id == source.team_id), None)
            if team is None:
                raise ValueError("Команда-исполнитель не входит в данный PI-цикл")
        else:
            team = resolve_cycle_team(teams_by_key, teams_by_name, source.tribe, source.team)
        record = existing_by_id.get(source.id) if source.id else existing_by_team.get(team.id)
        if source.id and record is None:
            raise ValueError("ID исполнителя не относится к этой инициативе")
        if record is None:
            record = InitiativeExecutor(id=uuid.uuid4(), team_id=team.id)
        if record.id in used or any(value.team_id == team.id for value in result):
            raise ValueError(f"Команда-исполнитель включена более одного раза: {team.name}")
        used.add(record.id)
        record.team_id = team.id
        record.effort_by_competency = normalized_effort(
            source.effort_by_competency,
            competencies_by_team.get(team.id, set()),
            f"Pre PI {item.issue_key} / {team.name}",
        )
        record.sort_order = position
        existing_attractions = {row.id: row for row in record.attraction_requests}
        natural_attractions = {
            (row.target_initiative_id, row.target_team_id, row.sprint_index): row
            for row in record.attraction_requests
        }
        attraction_result: list[InitiativeAttraction] = []
        attraction_keys: set[tuple[uuid.UUID, uuid.UUID, int]] = set()
        for attraction_position, source_attraction in enumerate(source.attractions):
            target = initiatives_by_id.get(source_attraction.target_initiative_id) if source_attraction.target_initiative_id else initiatives_by_key.get(source_attraction.issue_key.strip().casefold())
            if target is None:
                raise ValueError("Инициатива для привлечения не найдена в данном PI-цикле")
            if target.id == item.id:
                raise ValueError("Инициатива не может привлекать сама себя")
            target_team = None
            if source_attraction.target_team_id:
                target_team = next((value for value in teams_by_key.values() if value.id == source_attraction.target_team_id), None)
            elif source_attraction.team.strip():
                target_team = resolve_cycle_team(teams_by_key, teams_by_name, "", source_attraction.team)
            if target_team is None:
                raise ValueError("Укажите команду-цель привлечения")
            if source_attraction.sprint_index is None:
                raise ValueError("Укажите спринт привлечения")
            validate_sprint_position(cycle, source_attraction.sprint_index, None, "Привлечение")
            key = (target.id, target_team.id, source_attraction.sprint_index)
            if key in attraction_keys:
                raise ValueError("Дублирующийся запрос на привлечение")
            attraction_keys.add(key)
            attraction = existing_attractions.get(source_attraction.id) if source_attraction.id else natural_attractions.get(key)
            if source_attraction.id and attraction is None:
                raise ValueError("ID привлечения не относится к этому исполнителю")
            if attraction is None:
                attraction = InitiativeAttraction(id=uuid.uuid4(), approval_status="pending")
            attraction.target_initiative_id = target.id
            attraction.target_team_id = target_team.id
            attraction.sprint_index = source_attraction.sprint_index
            attraction.sort_order = attraction_position
            attraction_result.append(attraction)
        record.attraction_requests = attraction_result
        result.append(record)
    item.executors = result


async def update_pre_pi_initiative(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    payload: PrePiInitiativeCommand,
) -> PrePiRead:
    item = await _initiative_or_error(session, cycle.id, initiative_id)
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_version", "executors"})
    owner_team_id = changes.pop("owner_team_id", None) if "owner_team_id" in changes else None
    if "owner_team_id" in payload.model_fields_set:
        cycle_teams = await _cycle_teams(session, cycle.id)
        if owner_team_id is not None and owner_team_id not in {row.team_id for row in cycle_teams}:
            raise ValueError("Команда-владелец не входит в данный PI-цикл")
        item.owner_team_id = owner_team_id
    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip() if field not in {"description", "hypothesis", "redesign", "comment"} else value
        if field == "status":
            validate_status_transition(item.status, value)
        setattr(item, field, value)
    if payload.executors is not None:
        await _replace_executors(session, cycle, item, payload.executors)
    await session.commit()
    return await read_pre_pi(session, cycle)


async def _normalize_block_orders(session: AsyncSession, cycle_id: uuid.UUID) -> None:
    rows = await _initiatives_query(session, cycle_id)
    for is_planned in (True, False):
        for position, item in enumerate(row for row in rows if row.pre_planned is is_planned):
            item.sort_order = position


async def _delete_or_unlink_goals_for_initiatives(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    initiative_ids: Iterable[uuid.UUID],
) -> None:
    ids = list(initiative_ids)
    if not ids:
        return
    link_rows = list(
        (
            await session.scalars(
                select(PiGoalInitiative).where(PiGoalInitiative.initiative_id.in_(ids))
            )
        ).all()
    )
    affected_goal_ids = {link.goal_id for link in link_rows}
    for link in link_rows:
        await session.delete(link)
    await session.flush()

    legacy_goals = list(
        (
            await session.scalars(
                select(PiGoal)
                .options(selectinload(PiGoal.initiative_links))
                .where(PiGoal.cycle_id == cycle_id, PiGoal.initiative_id.in_(ids))
            )
        ).all()
    )
    linked_goals = []
    if affected_goal_ids:
        linked_goals = list(
            (
                await session.scalars(
                    select(PiGoal)
                    .options(selectinload(PiGoal.initiative_links))
                    .where(PiGoal.cycle_id == cycle_id, PiGoal.id.in_(affected_goal_ids))
                )
            ).all()
        )
    for goal in {goal.id: goal for goal in [*legacy_goals, *linked_goals]}.values():
        remaining = [link for link in goal.initiative_links if link.initiative_id not in ids]
        if remaining:
            goal.initiative_id = remaining[0].initiative_id
        else:
            await session.delete(goal)


async def move_pre_pi_initiative(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    payload: PrePiMoveCommand,
) -> PrePiRead:
    item = await _initiative_or_error(session, cycle.id, initiative_id)
    to_planned = payload.target_block == "planned"
    if not to_planned and item.on_board:
        affected = [{"kind": "initiative", "id": str(item.id), "label": item.issue_key}]
        if not payload.confirm_cascade:
            raise PrePiCascadeRequired(
                "Возврат опубликованной инициативы снимет её с досок и удалит связанные цели",
                affected,
            )
        await _delete_or_unlink_goals_for_initiatives(session, cycle.id, [item.id])
        item.on_board = False
        item.agreed = False
    item.pre_planned = to_planned
    item.status = "planned" if to_planned else "backlog"
    rows = await _initiatives_query(session, cycle.id)
    target = [row for row in rows if row.pre_planned is to_planned and row.id != item.id]
    index = len(target)
    if payload.before_id is not None:
        index = next((position for position, row in enumerate(target) if row.id == payload.before_id), -1)
        if index < 0:
            raise ValueError("Целевая позиция не входит в выбранный блок")
    target.insert(index, item)
    for position, row in enumerate(target):
        row.sort_order = position
    await _normalize_block_orders(session, cycle.id)
    await delete_dangling_connections(session, cycle.id)
    await session.commit()
    return await read_pre_pi(session, cycle)


async def delete_pre_pi_initiative(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    payload: PrePiDeleteCommand,
) -> PrePiRead:
    item = await _initiative_or_error(session, cycle.id, initiative_id)
    legacy_goals = list((await session.scalars(select(PiGoal).where(PiGoal.initiative_id == item.id))).all())
    linked_goal_ids = [
        row.goal_id
        for row in (
            await session.scalars(
                select(PiGoalInitiative).where(PiGoalInitiative.initiative_id == item.id)
            )
        ).all()
    ]
    linked_goals = []
    if linked_goal_ids:
        linked_goals = list(
            (
                await session.scalars(
                    select(PiGoal).where(PiGoal.id.in_(linked_goal_ids))
                )
            ).all()
        )
    goals = list({goal.id: goal for goal in [*legacy_goals, *linked_goals]}.values())
    affected = []
    if item.on_board:
        affected.append({"kind": "board", "id": str(item.id), "label": item.issue_key})
    affected.extend({"kind": "goal", "id": str(row.id), "label": row.title} for row in goals)
    if (affected or item.stories or item.work_items) and not payload.confirm_cascade:
        raise PrePiCascadeRequired(
            "Удаление инициативы затронет опубликованные данные",
            affected,
        )
    await _delete_or_unlink_goals_for_initiatives(session, cycle.id, [item.id])
    await session.delete(item)
    await session.flush()
    await _normalize_block_orders(session, cycle.id)
    await delete_dangling_connections(session, cycle.id)
    await session.commit()
    return await read_pre_pi(session, cycle)


async def replace_pre_pi(session: AsyncSession, cycle: PiCycle, payload: PrePiWrite) -> PrePiRead:
    """Compatibility bulk command; the active frontend uses focused commands."""
    normalized_keys = [row.issue_key.strip().casefold() for row in payload.initiatives]
    if len(normalized_keys) != len(set(normalized_keys)):
        raise ValueError("Issue должен быть уникален в пределах PI-цикла")
    existing = await _initiatives_query(session, cycle.id)
    by_id = {row.id: row for row in existing}
    by_key = {row.issue_key.casefold(): row for row in existing}
    used_ids: set[uuid.UUID] = set()
    cycle_teams = await _cycle_teams(session, cycle.id)
    teams_by_id = {row.team_id: row.team for row in cycle_teams}
    teams_by_key, teams_by_name, _ = await cycle_team_context(session, cycle.id)
    for position, source in enumerate(payload.initiatives):
        item = by_id.get(source.id) if source.id else by_key.get(source.issue_key.strip().casefold())
        if source.id and item is None:
            raise ValueError("ID инициативы не найден в данном PI-цикле")
        if item is None:
            item = Initiative(id=uuid.uuid4(), cycle_id=cycle.id, issue_key=source.issue_key.strip(), title="")
            session.add(item)
            item.executors = []
        used_ids.add(item.id)
        owner = None
        if source.owner_team.strip():
            owner = resolve_cycle_team(teams_by_key, teams_by_name, source.owner_tribe, source.owner_team)
        item.issue_key = source.issue_key.strip()
        for field in (
            "title", "description", "product", "initiative_type", "status", "goal_text",
            "metric", "current_value", "target_value", "hypothesis", "redesign",
            "customer_priority", "team_priority", "estimate", "comment", "pre_planned",
            "on_board", "agreed", "sprint_index", "week_index",
        ):
            setattr(item, field, getattr(source, field))
        item.owner_team_id = owner.id if owner else None
        item.tags = _clean_unique(source.tags)
        item.sort_order = source.sort_order if source.sort_order is not None else position
        validate_sprint_position(cycle, item.sprint_index, item.week_index, f"Инициатива {item.issue_key}")
        await _replace_executors(session, cycle, item, source.executors)
    removed = [row for row in existing if row.id not in used_ids]
    if removed:
        await _delete_or_unlink_goals_for_initiatives(
            session,
            cycle.id,
            [row.id for row in removed],
        )
        for row in removed:
            await session.delete(row)
    cycle.initiatives_initialized = True
    await session.flush()
    await _normalize_block_orders(session, cycle.id)
    await delete_dangling_connections(session, cycle.id)
    await session.commit()
    return await read_pre_pi(session, cycle)
