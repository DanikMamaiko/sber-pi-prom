import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.models.pi_cycle import (
    Initiative,
    InitiativeAttraction,
    InitiativeExecutor,
    PiCycle,
    PiCycleTeam,
    PiGoal,
    PiGoalInitiative,
    Team,
    Tribe,
)
from app.schemas.pi_cycle import (
    GoalCreateCommand,
    GoalDeleteCommand,
    GoalLinkCommand,
    GoalReorderCommand,
    GoalStatusCommand,
    GoalUnlinkCommand,
    GoalUpdateCommand,
    GoalsItemRead,
    GoalsRead,
    GoalsWrite,
    PrePiSubmitRead,
    PrePiSubmitWrite,
)
from app.services.pre_pi import read_pre_pi
from app.services.validation import (
    cycle_team_context,
    resolve_cycle_team,
    validate_sprint_position,
)


DEV_FUNCTIONALITY_TYPE = "Развитие функционала"
AGILE_REQUIRED_FIELDS = (
    ("cel", "Цель/Веха", "goal_text"),
    ("metric", "Метрика", "metric"),
    ("fact", "AS IS", "current_value"),
    ("plan", "TO BE", "target_value"),
)
IT_REQUIRED_FIELDS = (("cel", "Цель/Веха", "goal_text"),)


class PrePiValidationError(ValueError):
    def __init__(self, problems: list[dict]):
        super().__init__("Заполните обязательные поля Pre PI")
        self.problems = problems


class GoalsCascadeRequired(ValueError):
    def __init__(self, message: str, affected: list[dict]):
        super().__init__(message)
        self.message = message
        self.affected = affected


async def _goals_query(session: AsyncSession, cycle_id: uuid.UUID) -> list[PiGoal]:
    return list(
        (
            await session.scalars(
                select(PiGoal)
                .options(
                    selectinload(PiGoal.tribe),
                    selectinload(PiGoal.team).selectinload(Team.tribe),
                    selectinload(PiGoal.initiative),
                    selectinload(PiGoal.initiative_links).selectinload(
                        PiGoalInitiative.initiative
                    ),
                )
                .where(PiGoal.cycle_id == cycle_id)
                .order_by(PiGoal.sort_order, PiGoal.created_at, PiGoal.id)
            )
        ).all()
    )


async def read_goals(session: AsyncSession, cycle: PiCycle) -> GoalsRead:
    rows: list[GoalsItemRead] = []
    for goal in await _goals_query(session, cycle.id):
        linked_initiatives = [link.initiative for link in goal.initiative_links]
        if not linked_initiatives and goal.initiative_id is not None and goal.initiative is not None:
            linked_initiatives = [goal.initiative]
        initiative = linked_initiatives[0] if linked_initiatives else None
        team = goal.team
        tribe_name = ""
        if team and team.tribe:
            tribe_name = team.tribe.name
        elif goal.tribe:
            tribe_name = goal.tribe.name
        rows.append(
            GoalsItemRead(
                id=goal.id,
                tribe_id=goal.tribe_id,
                team_id=goal.team_id,
                initiative_id=initiative.id if initiative else None,
                initiative_ids=[initiative.id for initiative in linked_initiatives],
                tribe=tribe_name,
                team=team.name if team else "",
                issue_key=initiative.issue_key if initiative else "",
                initiative_title=initiative.title if initiative else "",
                title=goal.title,
                goal_text=goal.title or (initiative.goal_text if initiative else ""),
                product=goal.product or (initiative.product if initiative else ""),
                metric=goal.metric,
                current_value=goal.current_value,
                target_value=goal.target_value,
                hypothesis=goal.hypothesis,
                redesign=goal.redesign,
                owner=goal.owner,
                business_value=goal.business_value,
                status=goal.status,
                category=goal.category,
                sort_order=goal.sort_order,
            )
        )
    return GoalsRead(
        initialized=cycle.goals_initialized,
        version=cycle.version,
        goals=rows,
        reference_data=await _goals_reference_data(session, cycle),
    )


async def _goals_reference_data(session: AsyncSession, cycle: PiCycle) -> dict:
    cycle_teams = (
        await session.scalars(
            select(PiCycleTeam)
            .options(selectinload(PiCycleTeam.team).selectinload(Team.tribe))
            .where(PiCycleTeam.cycle_id == cycle.id)
            .order_by(PiCycleTeam.sort_order, PiCycleTeam.id)
        )
    ).all()
    initiatives = (
        await session.scalars(
            select(Initiative)
            .options(selectinload(Initiative.owner_team).selectinload(Team.tribe))
            .where(Initiative.cycle_id == cycle.id)
            .order_by(Initiative.sort_order, Initiative.created_at, Initiative.id)
        )
    ).all()
    tribes_by_id: dict[uuid.UUID, Tribe] = {}
    teams = []
    for row in cycle_teams:
        if row.team and row.team.tribe:
            tribes_by_id[row.team.tribe.id] = row.team.tribe
            teams.append(
                {
                    "id": row.team.id,
                    "cycle_team_id": row.id,
                    "tribe_id": row.team.tribe.id,
                    "tribe": row.team.tribe.name,
                    "name": row.team.name,
                    "type": row.team_type or row.team.team_type,
                    "excluded_from_goals": row.excluded_from_goals,
                    "sort_order": row.sort_order,
                }
            )
    return {
        "tribes": [
            {"id": tribe.id, "name": tribe.name}
            for tribe in sorted(tribes_by_id.values(), key=lambda item: item.name)
        ],
        "teams": teams,
        "initiatives": [
            {
                "id": initiative.id,
                "issue_key": initiative.issue_key,
                "title": initiative.title,
                "owner_team_id": initiative.owner_team_id,
                "owner_team": initiative.owner_team.name if initiative.owner_team else "",
                "owner_tribe_id": initiative.owner_team.tribe_id if initiative.owner_team else None,
                "owner_tribe": initiative.owner_team.tribe.name
                if initiative.owner_team and initiative.owner_team.tribe
                else "",
            }
            for initiative in initiatives
        ],
        "statuses": ["planned", "in_progress", "done", "cancelled"],
        "categories": ["committed", "stretch"],
    }


async def _resolve_team(
    session: AsyncSession,
    tribe_name: str,
    team_name: str,
) -> Team:
    team = await session.scalar(
        select(Team)
        .join(Tribe, Team.tribe_id == Tribe.id)
        .where(Tribe.name == tribe_name.strip(), Team.name == team_name.strip())
    )
    if team is None:
        raise ValueError(f"Команда не настроена для данного PI-цикла: {tribe_name} / {team_name}")
    return team


async def _resolve_initiative(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    issue_key: str,
) -> Initiative:
    initiative = await session.scalar(
        select(Initiative).where(
            Initiative.cycle_id == cycle_id,
            Initiative.issue_key == issue_key.strip(),
        )
    )
    if initiative is None:
        raise ValueError(f"Инициатива не найдена в данном PI-цикле: {issue_key}")
    return initiative


def _copy_to_goal(goal: PiGoal, initiative: Initiative, sort_order: int) -> None:
    goal.title = initiative.goal_text or ""
    goal.metric = initiative.metric or ""
    goal.current_value = initiative.current_value or ""
    goal.target_value = initiative.target_value or ""
    goal.hypothesis = initiative.hypothesis or ""
    goal.redesign = initiative.redesign or ""
    goal.product = initiative.product or ""
    goal.sort_order = sort_order


async def _cycle_team_by_id(
    session: AsyncSession,
    cycle: PiCycle,
    team_id: uuid.UUID | None,
) -> Team | None:
    if team_id is None:
        return None
    cycle_team = await session.scalar(
        select(PiCycleTeam)
        .options(selectinload(PiCycleTeam.team))
        .where(PiCycleTeam.cycle_id == cycle.id, PiCycleTeam.team_id == team_id)
    )
    if cycle_team is None:
        raise ValueError("Команда цели не входит в данный PI-цикл")
    return cycle_team.team


async def _cycle_tribe_by_id(
    session: AsyncSession,
    cycle: PiCycle,
    tribe_id: uuid.UUID | None,
) -> Tribe | None:
    if tribe_id is None:
        return None
    tribe = await session.get(Tribe, tribe_id)
    if tribe is None:
        raise ValueError("Трайб цели не найден")
    exists = await session.scalar(
        select(PiCycleTeam)
        .join(Team, PiCycleTeam.team_id == Team.id)
        .where(PiCycleTeam.cycle_id == cycle.id, Team.tribe_id == tribe_id)
    )
    if exists is None:
        raise ValueError("Трайб цели не входит в данный PI-цикл")
    return tribe


async def _cycle_initiatives_by_ids(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_ids: list[uuid.UUID],
) -> list[Initiative]:
    seen: list[uuid.UUID] = []
    for initiative_id in initiative_ids:
        if initiative_id not in seen:
            seen.append(initiative_id)
    if not seen:
        return []
    initiatives = (
        await session.scalars(
            select(Initiative).where(
                Initiative.cycle_id == cycle.id,
                Initiative.id.in_(seen),
            )
        )
    ).all()
    by_id = {initiative.id: initiative for initiative in initiatives}
    missing = [str(initiative_id) for initiative_id in seen if initiative_id not in by_id]
    if missing:
        raise ValueError("Инициатива цели не входит в данный PI-цикл: " + ", ".join(missing))
    return [by_id[initiative_id] for initiative_id in seen]


def _affected_initiatives(goal: PiGoal) -> list[dict]:
    linked = [link.initiative for link in goal.initiative_links]
    if not linked and goal.initiative is not None:
        linked = [goal.initiative]
    return [
        {"id": str(initiative.id), "issue_key": initiative.issue_key, "title": initiative.title}
        for initiative in linked
    ]


def _sync_goal_to_initiatives(goal: PiGoal) -> None:
    initiatives = [link.initiative for link in goal.initiative_links]
    if not initiatives and goal.initiative is not None:
        initiatives = [goal.initiative]
    for initiative in initiatives:
        initiative.goal_text = goal.title
        initiative.product = goal.product
        initiative.metric = goal.metric
        initiative.current_value = goal.current_value
        initiative.target_value = goal.target_value
        initiative.hypothesis = goal.hypothesis
        initiative.redesign = goal.redesign


async def _set_goal_links(
    session: AsyncSession,
    goal: PiGoal,
    initiatives: list[Initiative],
) -> None:
    current_links = list(goal.__dict__.get("initiative_links") or [])
    existing_by_initiative = {link.initiative_id: link for link in current_links}
    wanted = {initiative.id for initiative in initiatives}
    for link in current_links:
        if link.initiative_id not in wanted:
            await session.delete(link)
    next_links = [
        existing_by_initiative[initiative.id]
        if initiative.id in existing_by_initiative
        else PiGoalInitiative(goal_id=goal.id, initiative_id=initiative.id)
        for initiative in initiatives
    ]
    for index, link in enumerate(next_links):
        link.sort_order = index
        link.initiative = initiatives[index]
        session.add(link)
    set_committed_value(goal, "initiative_links", next_links)
    goal.initiative_id = initiatives[0].id if initiatives else None


async def _get_goal(session: AsyncSession, cycle: PiCycle, goal_id: uuid.UUID) -> PiGoal:
    goal = await session.scalar(
        select(PiGoal)
        .options(
            selectinload(PiGoal.initiative),
            selectinload(PiGoal.initiative_links).selectinload(PiGoalInitiative.initiative),
        )
        .where(PiGoal.cycle_id == cycle.id, PiGoal.id == goal_id)
    )
    if goal is None:
        raise ValueError("Цель не найдена в данном PI-цикле")
    return goal


async def create_goal_command(
    session: AsyncSession,
    cycle: PiCycle,
    payload: GoalCreateCommand,
) -> GoalsRead:
    team = await _cycle_team_by_id(session, cycle, payload.team_id)
    tribe_id = payload.tribe_id
    if team is not None:
        tribe_id = team.tribe_id
    await _cycle_tribe_by_id(session, cycle, tribe_id)
    initiatives = await _cycle_initiatives_by_ids(session, cycle, payload.initiative_ids)
    max_sort_order = await session.scalar(
        select(PiGoal.sort_order)
        .where(PiGoal.cycle_id == cycle.id)
        .order_by(PiGoal.sort_order.desc())
        .limit(1)
    )
    goal = PiGoal(
        id=uuid.uuid4(),
        cycle_id=cycle.id,
        tribe_id=tribe_id,
        team_id=team.id if team else None,
        title=payload.title.strip(),
        product=payload.product.strip(),
        metric=payload.metric.strip(),
        current_value=payload.current_value.strip(),
        target_value=payload.target_value.strip(),
        hypothesis=payload.hypothesis,
        redesign=payload.redesign,
        owner=payload.owner.strip(),
        business_value=payload.business_value,
        status=payload.status,
        category=payload.category,
        sort_order=(max_sort_order + 1 if max_sort_order is not None else 0),
    )
    session.add(goal)
    await session.flush()
    await _set_goal_links(session, goal, initiatives)
    _sync_goal_to_initiatives(goal)
    cycle.goals_initialized = True
    await session.commit()
    return await read_goals(session, cycle)


async def update_goal_command(
    session: AsyncSession,
    cycle: PiCycle,
    goal_id: uuid.UUID,
    payload: GoalUpdateCommand,
) -> GoalsRead:
    goal = await _get_goal(session, cycle, goal_id)
    data = payload.model_dump(exclude_unset=True, exclude={"expected_version", "confirm_cascade"})
    if "team_id" in data:
        team = await _cycle_team_by_id(session, cycle, payload.team_id)
        goal.team_id = team.id if team else None
        goal.tribe_id = team.tribe_id if team else goal.tribe_id
    if "tribe_id" in data and "team_id" not in data:
        await _cycle_tribe_by_id(session, cycle, payload.tribe_id)
        goal.tribe_id = payload.tribe_id
    if "initiative_ids" in data:
        old_ids = {link.initiative_id for link in goal.initiative_links}
        new_ids = set(payload.initiative_ids or [])
        removed = old_ids - new_ids
        if removed and not payload.confirm_cascade:
            raise GoalsCascadeRequired(
                "Изменение связей цели требует подтверждения",
                [
                    {"id": item["id"], "issue_key": item["issue_key"], "title": item["title"]}
                    for item in _affected_initiatives(goal)
                    if uuid.UUID(item["id"]) in removed
                ],
            )
        initiatives = await _cycle_initiatives_by_ids(session, cycle, payload.initiative_ids or [])
        await _set_goal_links(session, goal, initiatives)
    for field in (
        "title",
        "product",
        "metric",
        "current_value",
        "target_value",
        "hypothesis",
        "redesign",
        "owner",
        "business_value",
        "status",
        "category",
    ):
        if field in data:
            value = data[field]
            setattr(goal, field, value.strip() if isinstance(value, str) else value)
    _sync_goal_to_initiatives(goal)
    cycle.goals_initialized = True
    await session.commit()
    return await read_goals(session, cycle)


async def delete_goal_command(
    session: AsyncSession,
    cycle: PiCycle,
    goal_id: uuid.UUID,
    payload: GoalDeleteCommand,
) -> GoalsRead:
    goal = await _get_goal(session, cycle, goal_id)
    affected = _affected_initiatives(goal)
    if affected and not payload.confirm_cascade:
        raise GoalsCascadeRequired("Удаление цели требует подтверждения", affected)
    await session.delete(goal)
    cycle.goals_initialized = True
    await session.commit()
    return await read_goals(session, cycle)


async def reorder_goals_command(
    session: AsyncSession,
    cycle: PiCycle,
    payload: GoalReorderCommand,
) -> GoalsRead:
    goals = (
        await session.scalars(select(PiGoal).where(PiGoal.cycle_id == cycle.id))
    ).all()
    by_id = {goal.id: goal for goal in goals}
    if set(payload.goal_ids) != set(by_id):
        raise ValueError("Порядок должен включать все цели данного PI-цикла")
    for index, goal_id in enumerate(payload.goal_ids):
        by_id[goal_id].sort_order = index
    cycle.goals_initialized = True
    await session.commit()
    return await read_goals(session, cycle)


async def update_goal_status_command(
    session: AsyncSession,
    cycle: PiCycle,
    goal_id: uuid.UUID,
    payload: GoalStatusCommand,
) -> GoalsRead:
    goal = await _get_goal(session, cycle, goal_id)
    goal.status = payload.status
    cycle.goals_initialized = True
    await session.commit()
    return await read_goals(session, cycle)


async def add_goal_link_command(
    session: AsyncSession,
    cycle: PiCycle,
    goal_id: uuid.UUID,
    payload: GoalLinkCommand,
) -> GoalsRead:
    goal = await _get_goal(session, cycle, goal_id)
    initiatives = await _cycle_initiatives_by_ids(session, cycle, [payload.initiative_id])
    if payload.initiative_id not in {link.initiative_id for link in goal.initiative_links}:
        goal.initiative_links.append(
            PiGoalInitiative(
                goal_id=goal.id,
                initiative_id=payload.initiative_id,
                initiative=initiatives[0],
                sort_order=len(goal.initiative_links),
            )
        )
    goal.initiative_id = goal.initiative_links[0].initiative_id if goal.initiative_links else None
    _sync_goal_to_initiatives(goal)
    cycle.goals_initialized = True
    await session.commit()
    return await read_goals(session, cycle)


async def remove_goal_link_command(
    session: AsyncSession,
    cycle: PiCycle,
    goal_id: uuid.UUID,
    initiative_id: uuid.UUID,
    payload: GoalUnlinkCommand,
) -> GoalsRead:
    goal = await _get_goal(session, cycle, goal_id)
    link = next((item for item in goal.initiative_links if item.initiative_id == initiative_id), None)
    if link is None:
        raise ValueError("Связь цели с инициативой не найдена")
    if not payload.confirm_cascade:
        raise GoalsCascadeRequired("Удаление связи цели требует подтверждения", _affected_initiatives(goal))
    await session.delete(link)
    remaining = [item for item in goal.initiative_links if item.initiative_id != initiative_id]
    goal.initiative_id = remaining[0].initiative_id if remaining else None
    cycle.goals_initialized = True
    await session.commit()
    return await read_goals(session, cycle)


async def replace_goals(
    session: AsyncSession,
    cycle: PiCycle,
    payload: GoalsWrite,
) -> GoalsRead:
    normalized_keys = [
        (row.tribe.strip().casefold(), row.team.strip().casefold(), row.issue_key.strip().casefold())
        for row in payload.goals
    ]
    if len(normalized_keys) != len(set(normalized_keys)):
        raise ValueError("Инициатива может встречаться в целях команды только один раз")

    existing = await _goals_query(session, cycle.id)
    by_id = {row.id: row for row in existing}
    by_pair = {
        (row.team_id, row.initiative_id): row
        for row in existing
        if row.team_id and row.initiative_id
    }
    used_ids: set[uuid.UUID] = set()

    for position, source in enumerate(payload.goals):
        team = await _resolve_team(session, source.tribe, source.team)
        cycle_team = await session.scalar(
            select(PiCycleTeam).where(
                PiCycleTeam.cycle_id == cycle.id,
                PiCycleTeam.team_id == team.id,
            )
        )
        if cycle_team is None:
            raise ValueError(
                f"Команда не входит в данный PI-цикл: {source.tribe} / {source.team}"
            )
        initiative = await _resolve_initiative(session, cycle.id, source.issue_key)
        goal = by_id.get(source.id) if source.id else None
        pair_match = by_pair.get((team.id, initiative.id))
        if goal is not None and pair_match is not None and goal.id != pair_match.id:
            raise ValueError(f"Запись цели уже существует: {source.team} / {source.issue_key}")
        if goal is None:
            goal = pair_match
        if goal is None:
            goal = PiGoal(
                id=uuid.uuid4(),
                cycle_id=cycle.id,
                team_id=team.id,
                tribe_id=team.tribe_id,
                initiative_id=initiative.id,
                title="",
            )
            session.add(goal)
        if goal.id in used_ids:
            raise ValueError(f"Запись цели включена более одного раза: {source.issue_key}")
        used_ids.add(goal.id)

        goal.team_id = team.id
        goal.tribe_id = team.tribe_id
        goal.initiative_id = initiative.id
        goal.owner = source.owner.strip()
        goal.business_value = source.business_value
        goal.status = source.status
        goal.category = source.category
        initiative.goal_text = source.goal_text.strip()
        initiative.product = source.product.strip()
        initiative.metric = source.metric.strip()
        initiative.current_value = source.current_value.strip()
        initiative.target_value = source.target_value.strip()
        initiative.hypothesis = source.hypothesis
        initiative.redesign = source.redesign
        _copy_to_goal(goal, initiative, source.sort_order if source.sort_order is not None else position)
        if not any(link.initiative_id == initiative.id for link in goal.initiative_links):
            goal.initiative_links.append(
                PiGoalInitiative(
                    goal_id=goal.id,
                    initiative_id=initiative.id,
                    initiative=initiative,
                    sort_order=0,
                )
            )

    for goal in existing:
        if goal.id not in used_ids:
            await session.delete(goal)

    cycle.goals_initialized = True
    await session.commit()
    return await read_goals(session, cycle)


async def submit_pre_pi(
    session: AsyncSession,
    cycle: PiCycle,
    payload: PrePiSubmitWrite,
) -> PrePiSubmitRead:
    team_keys = [
        (row.tribe.strip().casefold(), row.name.strip().casefold())
        for row in payload.teams
    ]
    if len(team_keys) != len(set(team_keys)):
        raise ValueError("Команда может быть отправлена только один раз")

    selected: list[tuple[Team, str]] = []
    for source in payload.teams:
        team = await _resolve_team(session, source.tribe, source.name)
        cycle_team = await session.scalar(
            select(PiCycleTeam).where(
                PiCycleTeam.cycle_id == cycle.id,
                PiCycleTeam.team_id == team.id,
            )
        )
        if cycle_team is None:
            raise ValueError(f"Команда не входит в данный PI-цикл: {source.name}")
        selected.append((team, cycle_team.team_type or team.team_type))

    initiatives = list(
        (
            await session.scalars(
                select(Initiative)
                .options(
                    selectinload(Initiative.executors).selectinload(InitiativeExecutor.team),
                    selectinload(Initiative.executors)
                    .selectinload(InitiativeExecutor.attraction_requests)
                    .selectinload(InitiativeAttraction.target_initiative),
                    selectinload(Initiative.executors)
                    .selectinload(InitiativeExecutor.attraction_requests)
                    .selectinload(InitiativeAttraction.target_team),
                    selectinload(Initiative.owner_team),
                )
                .where(Initiative.cycle_id == cycle.id)
                .order_by(Initiative.sort_order, Initiative.created_at, Initiative.id)
            )
        ).all()
    )
    problems: list[dict] = []
    candidates: list[tuple[Team, Initiative]] = []
    for team, team_type in selected:
        required = IT_REQUIRED_FIELDS if team_type == "ИТ-проект" else AGILE_REQUIRED_FIELDS
        for initiative in initiatives:
            if not initiative.pre_planned or not any(ex.team_id == team.id for ex in initiative.executors):
                continue
            candidates.append((team, initiative))
            if initiative.initiative_type.strip() != DEV_FUNCTIONALITY_TYPE:
                continue
            missing = [
                {"key": ui_key, "label": label}
                for ui_key, label, attr in required
                if not str(getattr(initiative, attr) or "").strip()
            ]
            if missing:
                problems.append(
                    {"issue_key": initiative.issue_key, "team": team.name, "missing": missing}
                )
    if problems:
        raise PrePiValidationError(problems)

    existing_goals = await _goals_query(session, cycle.id)
    goals_by_pair = {
        (row.team_id, row.initiative_id): row
        for row in existing_goals
        if row.team_id and row.initiative_id
    }
    next_order: dict[uuid.UUID, int] = {}
    for goal in existing_goals:
        if goal.team_id:
            next_order[goal.team_id] = max(next_order.get(goal.team_id, 0), goal.sort_order + 1)

    goals_added = 0
    board_added = 0
    for team, initiative in candidates:
        pair = (team.id, initiative.id)
        goal = goals_by_pair.get(pair)
        if goal is None:
            goal = PiGoal(
                id=uuid.uuid4(),
                cycle_id=cycle.id,
                tribe_id=team.tribe_id,
                team_id=team.id,
                initiative_id=initiative.id,
                title="",
            )
            session.add(goal)
            goals_by_pair[pair] = goal
            goals_added += 1
        order = goal.sort_order if goal.id in {row.id for row in existing_goals} else next_order.get(team.id, 0)
        _copy_to_goal(goal, initiative, order)
        if not any(link.initiative_id == initiative.id for link in goal.initiative_links):
            goal.initiative_links.append(
                PiGoalInitiative(
                    goal_id=goal.id,
                    initiative_id=initiative.id,
                    initiative=initiative,
                    sort_order=0,
                )
            )
        next_order[team.id] = max(next_order.get(team.id, 0), order + 1)
        if not initiative.on_board:
            initiative.on_board = True
            initiative.status = "on_board"
            board_added += 1

    cycle.goals_initialized = True
    await session.commit()
    return PrePiSubmitRead(
        version=cycle.version,
        goals_added=goals_added,
        board_added=board_added,
        attractions_added=0,
        pre_pi=await read_pre_pi(session, cycle),
        goals=await read_goals(session, cycle),
    )
