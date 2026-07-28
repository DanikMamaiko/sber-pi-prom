import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    Initiative,
    InitiativeAttraction,
    InitiativeExecutor,
    PiCycle,
    PiCycleTeam,
    PiGoal,
    Team,
    Tribe,
)
from app.schemas.pi_cycle import (
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
        super().__init__("Required Pre PI fields are not filled")
        self.problems = problems


async def _goals_query(session: AsyncSession, cycle_id: uuid.UUID) -> list[PiGoal]:
    return list(
        (
            await session.scalars(
                select(PiGoal)
                .options(
                    selectinload(PiGoal.tribe),
                    selectinload(PiGoal.team).selectinload(Team.tribe),
                    selectinload(PiGoal.initiative),
                )
                .where(PiGoal.cycle_id == cycle_id)
                .order_by(PiGoal.sort_order, PiGoal.created_at, PiGoal.id)
            )
        ).all()
    )


async def read_goals(session: AsyncSession, cycle: PiCycle) -> GoalsRead:
    rows: list[GoalsItemRead] = []
    for goal in await _goals_query(session, cycle.id):
        initiative = goal.initiative
        team = goal.team
        if initiative is None or team is None:
            continue
        tribe_name = team.tribe.name if team.tribe else (goal.tribe.name if goal.tribe else "")
        rows.append(
            GoalsItemRead(
                id=goal.id,
                tribe=tribe_name,
                team=team.name,
                issue_key=initiative.issue_key,
                initiative_title=initiative.title,
                goal_text=initiative.goal_text or goal.title or "",
                product=initiative.product or goal.product or "",
                metric=initiative.metric or "",
                current_value=initiative.current_value or "",
                target_value=initiative.target_value or "",
                hypothesis=initiative.hypothesis or "",
                redesign=initiative.redesign or "",
                sort_order=goal.sort_order,
            )
        )
    return GoalsRead(initialized=cycle.goals_initialized, version=cycle.version, goals=rows)


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
        raise ValueError(f"Team is not configured for this PI cycle: {tribe_name} / {team_name}")
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
        raise ValueError(f"Initiative is not found in this PI cycle: {issue_key}")
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
        raise ValueError("An initiative can only occur once in a team's goals")

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
                f"Team is not part of this PI cycle: {source.tribe} / {source.team}"
            )
        initiative = await _resolve_initiative(session, cycle.id, source.issue_key)
        goal = by_id.get(source.id) if source.id else None
        pair_match = by_pair.get((team.id, initiative.id))
        if goal is not None and pair_match is not None and goal.id != pair_match.id:
            raise ValueError(f"Goal row already exists: {source.team} / {source.issue_key}")
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
            raise ValueError(f"Goal row is included more than once: {source.issue_key}")
        used_ids.add(goal.id)

        goal.team_id = team.id
        goal.tribe_id = team.tribe_id
        goal.initiative_id = initiative.id
        initiative.goal_text = source.goal_text.strip()
        initiative.product = source.product.strip()
        initiative.metric = source.metric.strip()
        initiative.current_value = source.current_value.strip()
        initiative.target_value = source.target_value.strip()
        initiative.hypothesis = source.hypothesis
        initiative.redesign = source.redesign
        _copy_to_goal(goal, initiative, source.sort_order if source.sort_order is not None else position)

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
        raise ValueError("A team can only be submitted once")

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
            raise ValueError(f"Team is not part of this PI cycle: {source.name}")
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
        next_order[team.id] = max(next_order.get(team.id, 0), order + 1)
        if not initiative.on_board:
            initiative.on_board = True
            initiative.status = "on_board"
            board_added += 1

    selected_ids = {team.id for team, _ in selected}
    selected_by_id = {team.id: team for team, _ in selected}
    attractions_added = 0
    for host in initiatives:
        matching_executor = next(
            (executor for executor in host.executors if executor.team_id in selected_ids),
            None,
        )
        if matching_executor is None:
            continue
        fallback_owner = host.owner_team_id or selected_by_id[matching_executor.team_id].id
        for executor in host.executors:
            for attraction in executor.attraction_requests:
                referenced = attraction.target_initiative
                validate_sprint_position(
                    cycle,
                    attraction.sprint_index,
                    None,
                    f"Attraction {referenced.issue_key}",
                )
                if referenced.owner_team_id is None:
                    referenced.owner_team_id = fallback_owner
                if not referenced.on_board:
                    referenced.on_board = True
                    referenced.status = "on_board"
                    referenced.sprint_index = attraction.sprint_index
                    referenced.week_index = None
                    attractions_added += 1

    cycle.goals_initialized = True
    await session.commit()
    return PrePiSubmitRead(
        version=cycle.version,
        goals_added=goals_added,
        board_added=board_added,
        attractions_added=attractions_added,
        pre_pi=await read_pre_pi(session, cycle),
        goals=await read_goals(session, cycle),
    )
