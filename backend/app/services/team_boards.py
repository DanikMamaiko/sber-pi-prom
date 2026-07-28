import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    Initiative,
    PiCycle,
    PiCycleCapacityMember,
    Story,
    WorkItem,
)
from app.schemas.pi_cycle import (
    TeamBoardInitiativeRead,
    TeamBoardsRead,
    TeamBoardsWrite,
)
from app.services.program_board import delete_dangling_connections
from app.services.validation import (
    cycle_team_context,
    normalized_effort,
    validate_sprint_position,
)


async def _initiatives_query(session: AsyncSession, cycle_id: uuid.UUID) -> list[Initiative]:
    return list(
        (
            await session.scalars(
                select(Initiative)
                .execution_options(populate_existing=True)
                .options(
                    selectinload(Initiative.executors),
                    selectinload(Initiative.stories),
                    selectinload(Initiative.work_items).selectinload(WorkItem.story),
                )
                .where(Initiative.cycle_id == cycle_id)
                .order_by(Initiative.sort_order, Initiative.created_at, Initiative.id)
            )
        ).all()
    )


async def read_team_boards(session: AsyncSession, cycle: PiCycle) -> TeamBoardsRead:
    rows: list[TeamBoardInitiativeRead] = []
    for initiative in await _initiatives_query(session, cycle.id):
        stories = sorted(initiative.stories, key=lambda row: (row.sort_order, row.created_at, row.id))
        work_items = sorted(
            initiative.work_items,
            key=lambda row: (row.sort_order, row.created_at, row.id),
        )
        rows.append(
            TeamBoardInitiativeRead(
                id=initiative.id,
                issue_key=initiative.issue_key,
                pre_planned=initiative.pre_planned,
                on_board=initiative.on_board,
                agreed=initiative.agreed,
                sprint_index=initiative.sprint_index,
                week_index=initiative.week_index,
                board_sort_order=initiative.board_sort_order,
                stories=[
                    {
                        "id": story.id,
                        "client_uid": story.client_uid,
                        "external_key": story.external_key or "",
                        "title": story.title or "",
                        "effort_by_competency": dict(story.effort_by_competency or {}),
                        "sprint_index": story.sprint_index,
                        "week_index": story.week_index,
                        "sort_order": story.sort_order,
                        "board_sort_order": story.board_sort_order,
                    }
                    for story in stories
                ],
                work_items=[
                    {
                        "id": item.id,
                        "client_uid": item.client_uid,
                        "story_client_uid": item.story.client_uid if item.story else None,
                        "assignee_name": item.assignee_name or "",
                        "competency": item.competency,
                        "effort": item.effort,
                        "sprint_index": item.sprint_index,
                        "week_index": item.week_index,
                        "sort_order": item.sort_order,
                        "board_sort_order": item.board_sort_order,
                    }
                    for item in work_items
                ],
            )
        )
    return TeamBoardsRead(
        initialized=cycle.boards_initialized,
        version=cycle.version,
        initiatives=rows,
    )


async def replace_team_boards(
    session: AsyncSession,
    cycle: PiCycle,
    payload: TeamBoardsWrite,
) -> TeamBoardsRead:
    issue_keys = [row.issue_key.strip().casefold() for row in payload.initiatives]
    if len(issue_keys) != len(set(issue_keys)):
        raise ValueError("An initiative can only occur once in the team boards payload")

    story_uids = [
        story.client_uid.strip().casefold()
        for initiative in payload.initiatives
        for story in initiative.stories
    ]
    if len(story_uids) != len(set(story_uids)):
        raise ValueError("Story UID must be unique inside a PI cycle")
    work_uids = [
        item.client_uid.strip().casefold()
        for initiative in payload.initiatives
        for item in initiative.work_items
    ]
    if len(work_uids) != len(set(work_uids)):
        raise ValueError("Work item UID must be unique inside a PI cycle")

    existing = await _initiatives_query(session, cycle.id)
    by_id = {row.id: row for row in existing}
    by_key = {row.issue_key.casefold(): row for row in existing}
    _, _, competencies_by_team = await cycle_team_context(session, cycle.id)
    capacity_members = list(
        (
            await session.scalars(
                select(PiCycleCapacityMember).where(
                    PiCycleCapacityMember.cycle_id == cycle.id
                )
            )
        ).all()
    )

    for source in payload.initiatives:
        issue_key = source.issue_key.strip()
        initiative = by_id.get(source.id) if source.id else None
        key_match = by_key.get(issue_key.casefold())
        if source.id is not None and initiative is None:
            raise ValueError(f"Initiative ID is not found in this PI cycle: {source.id}")
        if initiative is not None and key_match is not None and initiative.id != key_match.id:
            raise ValueError(f"Initiative ID does not match Issue ID: {issue_key}")
        if initiative is None:
            initiative = key_match
        if initiative is None:
            raise ValueError(f"Initiative is not found in this PI cycle: {issue_key}")

        validate_sprint_position(
            cycle,
            source.sprint_index,
            source.week_index,
            f"Initiative {issue_key}",
        )
        executor_team_ids = {executor.team_id for executor in initiative.executors}
        allowed_competencies: set[str] = set()
        for team_id in executor_team_ids:
            allowed_competencies.update(competencies_by_team.get(team_id, set()))
        roster = [
            member for member in capacity_members if member.team_id in executor_team_ids
        ]

        initiative.pre_planned = source.pre_planned
        initiative.on_board = source.on_board
        initiative.agreed = source.agreed
        initiative.sprint_index = source.sprint_index
        initiative.week_index = source.week_index
        initiative.board_sort_order = source.board_sort_order
        initiative.status = "on_board" if source.on_board else ("planned" if source.pre_planned else "backlog")

        existing_stories_by_id = {story.id: story for story in initiative.stories}
        existing_stories_by_uid = {story.client_uid.casefold(): story for story in initiative.stories}
        desired_stories: list[Story] = []
        desired_story_ids: set[uuid.UUID] = set()
        desired_stories_by_uid: dict[str, Story] = {}
        for position, source_story in enumerate(source.stories):
            uid = source_story.client_uid.strip()
            story = existing_stories_by_id.get(source_story.id) if source_story.id else None
            uid_match = existing_stories_by_uid.get(uid.casefold())
            if source_story.id is not None and story is None:
                raise ValueError(
                    f"Story ID is not found for initiative {issue_key}: {source_story.id}"
                )
            if story is not None and uid_match is not None and story.id != uid_match.id:
                raise ValueError(f"Story ID does not match client UID: {uid}")
            if story is None:
                story = uid_match
            if story is None:
                story = Story(
                    id=uuid.uuid4(),
                    initiative_id=initiative.id,
                    client_uid=uid,
                    title=source_story.title,
                )
                session.add(story)
            story.client_uid = uid
            story.external_key = source_story.external_key.strip()
            story.title = source_story.title.strip()
            validate_sprint_position(
                cycle,
                source_story.sprint_index,
                source_story.week_index,
                f"Story {uid}",
            )
            story.effort_by_competency = normalized_effort(
                source_story.effort_by_competency,
                allowed_competencies,
                f"Story {uid}",
            )
            story.sprint_index = source_story.sprint_index
            story.week_index = source_story.week_index
            story.sort_order = source_story.sort_order if source_story.sort_order is not None else position
            story.board_sort_order = source_story.board_sort_order
            desired_stories.append(story)
            desired_story_ids.add(story.id)
            desired_stories_by_uid[uid.casefold()] = story

        await session.flush()

        existing_items_by_id = {item.id: item for item in initiative.work_items}
        existing_items_by_uid = {item.client_uid.casefold(): item for item in initiative.work_items}
        desired_item_ids: set[uuid.UUID] = set()
        for position, source_item in enumerate(source.work_items):
            uid = source_item.client_uid.strip()
            item = existing_items_by_id.get(source_item.id) if source_item.id else None
            uid_match = existing_items_by_uid.get(uid.casefold())
            if source_item.id is not None and item is None:
                raise ValueError(
                    f"Work item ID is not found for initiative {issue_key}: {source_item.id}"
                )
            if item is not None and uid_match is not None and item.id != uid_match.id:
                raise ValueError(f"Work item ID does not match client UID: {uid}")
            if item is None:
                item = uid_match
            if item is None:
                item = WorkItem(
                    id=uuid.uuid4(),
                    initiative_id=initiative.id,
                    client_uid=uid,
                    competency=source_item.competency.strip().upper(),
                )
                session.add(item)
            story = None
            if source_item.story_client_uid:
                story = desired_stories_by_uid.get(source_item.story_client_uid.strip().casefold())
                if story is None:
                    raise ValueError(
                        f"Story UID is not found for work item {uid}: {source_item.story_client_uid}"
                    )
            validate_sprint_position(
                cycle,
                source_item.sprint_index,
                source_item.week_index,
                f"Work item {uid}",
            )
            competency = source_item.competency.strip().upper()
            if competency not in allowed_competencies:
                raise ValueError(
                    f"Work item {uid}: competency is not configured for an executor team: "
                    f"{competency}"
                )
            assignee_name = source_item.assignee_name.strip()
            if assignee_name and roster and not any(
                member.full_name.strip().casefold() == assignee_name.casefold()
                and member.competency.strip().upper() == competency
                for member in roster
            ):
                raise ValueError(
                    f"Work item {uid}: assignee is not available with competency {competency}"
                )
            item.client_uid = uid
            item.story_id = story.id if story else None
            item.assignee_name = assignee_name
            item.competency = competency
            item.effort = float(source_item.effort)
            item.sprint_index = source_item.sprint_index
            item.week_index = source_item.week_index
            item.sort_order = source_item.sort_order if source_item.sort_order is not None else position
            item.board_sort_order = source_item.board_sort_order
            desired_item_ids.add(item.id)

        for item in initiative.work_items:
            if item.id not in desired_item_ids:
                await session.delete(item)
        await session.flush()
        for story in initiative.stories:
            if story.id not in desired_story_ids:
                await session.delete(story)

    cycle.boards_initialized = True
    await delete_dangling_connections(session, cycle.id)
    await session.commit()
    return await read_team_boards(session, cycle)
