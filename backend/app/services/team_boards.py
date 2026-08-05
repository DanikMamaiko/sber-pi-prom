import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import (
    BoardConnection,
    Initiative,
    PiCycle,
    PiCycleCapacityMember,
    PiCycleTag,
    Story,
    WorkItem,
)
from app.schemas.pi_cycle import (
    TeamBoardInitiativeRead,
    TeamBoardsRead,
    TeamBoardsWrite,
    TeamBoardDeleteCommand,
    TeamBoardInitiativeCommand,
    TeamBoardStoryCreate,
    TeamBoardStoryUpdate,
    TeamBoardWorkItemCreate,
    TeamBoardWorkItemUpdate,
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
                approved_by=initiative.approved_by,
                approved_at=initiative.approved_at,
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
                        "assignee_member_id": item.assignee_member_id,
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
    approved_by: str | None = None,
) -> TeamBoardsRead:
    issue_keys = [row.issue_key.strip().casefold() for row in payload.initiatives]
    if len(issue_keys) != len(set(issue_keys)):
        raise ValueError("Инициатива может встречаться в составе командных досок только один раз")

    story_uids = [
        story.client_uid.strip().casefold()
        for initiative in payload.initiatives
        for story in initiative.stories
    ]
    if len(story_uids) != len(set(story_uids)):
        raise ValueError("UID истории должен быть уникален в пределах PI-цикла")
    work_uids = [
        item.client_uid.strip().casefold()
        for initiative in payload.initiatives
        for item in initiative.work_items
    ]
    if len(work_uids) != len(set(work_uids)):
        raise ValueError("UID задачи должен быть уникален в пределах PI-цикла")

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
            raise ValueError(f"ID инициативы не найден в данном PI-цикле: {source.id}")
        if initiative is not None and key_match is not None and initiative.id != key_match.id:
            raise ValueError(f"ID инициативы не соответствует Issue: {issue_key}")
        if initiative is None:
            initiative = key_match
        if initiative is None:
            raise ValueError(f"Инициатива не найдена в данном PI-цикле: {issue_key}")

        validate_sprint_position(
            cycle,
            source.sprint_index,
            source.week_index,
            f"Инициатива {issue_key}",
        )
        primary_executor = min(
            initiative.executors,
            key=lambda row: (row.sort_order, str(row.id)),
            default=None,
        )
        executor_team_ids = {primary_executor.team_id} if primary_executor else set()
        allowed_competencies: set[str] = (
            set(competencies_by_team.get(primary_executor.team_id, set()))
            if primary_executor
            else set()
        )
        roster = [
            member for member in capacity_members if member.team_id in executor_team_ids
        ]

        initiative.pre_planned = source.pre_planned
        initiative.on_board = source.on_board
        source_agreed = bool(source.agreed)
        if source_agreed:
            if not initiative.agreed or not initiative.approved_by or not initiative.approved_at:
                if approved_by:
                    initiative.approved_by = approved_by
                initiative.approved_at = datetime.now(timezone.utc)
        else:
            initiative.approved_by = None
            initiative.approved_at = None
        initiative.agreed = source_agreed
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
                    f"ID истории не найден для инициативы {issue_key}: {source_story.id}"
                )
            if story is not None and uid_match is not None and story.id != uid_match.id:
                raise ValueError(f"ID истории не соответствует клиентскому UID: {uid}")
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
                f"История {uid}",
            )
            story.effort_by_competency = normalized_effort(
                source_story.effort_by_competency,
                allowed_competencies,
                f"История {uid}",
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
                    f"ID задачи не найден для инициативы {issue_key}: {source_item.id}"
                )
            if item is not None and uid_match is not None and item.id != uid_match.id:
                raise ValueError(f"ID задачи не соответствует клиентскому UID: {uid}")
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
                        f"UID истории не найден для задачи {uid}: {source_item.story_client_uid}"
                    )
            validate_sprint_position(
                cycle,
                source_item.sprint_index,
                source_item.week_index,
                f"Задача {uid}",
            )
            competency = source_item.competency.strip().upper()
            if competency not in allowed_competencies:
                raise ValueError(
                    f"Задача {uid}: компетенция не настроена для команды-исполнителя: "
                    f"{competency}"
                )
            assignee_name = source_item.assignee_name.strip()
            assigned_member = None
            if source_item.assignee_member_id is not None:
                assigned_member = next(
                    (member for member in roster if member.id == source_item.assignee_member_id),
                    None,
                )
                if assigned_member is None:
                    raise ValueError(f"Задача {uid}: исполнитель не входит в команду-исполнитель")
                if assigned_member.competency.strip().upper() != competency:
                    raise ValueError(
                        f"Задача {uid}: компетенция исполнителя не совпадает с {competency}"
                    )
                assignee_name = assigned_member.full_name
            if assigned_member is None:
                assigned_member = _validate_assignee(
                    uid, assignee_name, competency, roster
                )
            item.client_uid = uid
            item.story_id = story.id if story else None
            item.assignee_member_id = assigned_member.id if assigned_member else None
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


class TeamBoardCascadeRequired(Exception):
    def __init__(self, message: str, affected: list[dict[str, str]]):
        super().__init__(message)
        self.message = message
        self.affected = affected


async def _initiative_for_command(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
) -> Initiative:
    initiative = await session.scalar(
        select(Initiative)
        .execution_options(populate_existing=True)
        .options(
            selectinload(Initiative.executors),
            selectinload(Initiative.stories),
            selectinload(Initiative.work_items).selectinload(WorkItem.story),
        )
        .where(Initiative.cycle_id == cycle.id, Initiative.id == initiative_id)
    )
    if initiative is None:
        raise ValueError("Инициатива не найдена в данном PI-цикле")
    if not initiative.on_board:
        raise ValueError("Инициатива не опубликована на командные доски")
    return initiative


async def _initiative_board_context(
    session: AsyncSession,
    cycle: PiCycle,
    initiative: Initiative,
) -> tuple[set[str], list[PiCycleCapacityMember]]:
    _, _, competencies_by_team = await cycle_team_context(session, cycle.id)
    primary_executor = min(
        initiative.executors,
        key=lambda row: (row.sort_order, str(row.id)),
        default=None,
    )
    team_ids = {primary_executor.team_id} if primary_executor else set()
    competencies: set[str] = (
        set(competencies_by_team.get(primary_executor.team_id, set()))
        if primary_executor
        else set()
    )
    members = list(
        (
            await session.scalars(
                select(PiCycleCapacityMember).where(
                    PiCycleCapacityMember.cycle_id == cycle.id,
                    PiCycleCapacityMember.team_id.in_(team_ids),
                )
            )
        ).all()
    ) if team_ids else []
    return competencies, members


async def _assert_client_uid_available(
    session: AsyncSession,
    cycle: PiCycle,
    model,
    client_uid: str,
    *,
    current_id: uuid.UUID | None = None,
) -> None:
    statement = (
        select(model.id)
        .join(Initiative, Initiative.id == model.initiative_id)
        .where(
            Initiative.cycle_id == cycle.id,
            model.client_uid.ilike(client_uid.strip()),
        )
    )
    if current_id is not None:
        statement = statement.where(model.id != current_id)
    if await session.scalar(statement):
        raise ValueError(f"Клиентский UID должен быть уникален в пределах PI-цикла: {client_uid}")


def _validate_assignee(
    uid: str,
    assignee_name: str,
    competency: str,
    roster: list[PiCycleCapacityMember],
) -> PiCycleCapacityMember | None:
    if not assignee_name:
        return None
    member = next(
        (
            row
            for row in roster
            if row.full_name.strip().casefold() == assignee_name.casefold()
            and row.competency.strip().upper() == competency
        ),
        None,
    )
    if member is None:
        raise ValueError(
            f"Задача {uid}: нет доступного исполнителя с компетенцией {competency}"
        )
    return member


def _resolve_assignee(
    uid: str,
    member_id: uuid.UUID | None,
    assignee_name: str,
    competency: str,
    roster: list[PiCycleCapacityMember],
) -> tuple[uuid.UUID | None, str]:
    if member_id is not None:
        member = next((row for row in roster if row.id == member_id), None)
        if member is None:
            raise ValueError(f"Задача {uid}: исполнитель не входит в команду-исполнитель")
        if member.competency.strip().upper() != competency:
            raise ValueError(
                f"Задача {uid}: компетенция исполнителя не совпадает с {competency}"
            )
        return member.id, member.full_name
    member = _validate_assignee(uid, assignee_name, competency, roster)
    return (member.id, member.full_name) if member else (None, "")


async def update_board_initiative(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    payload: TeamBoardInitiativeCommand,
    approved_by: str | None = None,
) -> TeamBoardsRead:
    initiative = await _initiative_for_command(session, cycle, initiative_id)
    fields = payload.model_fields_set
    if "title" in fields:
        initiative.title = (payload.title or "").strip()
    if "initiative_type" in fields:
        initiative.initiative_type = (payload.initiative_type or "").strip()
    if "comment" in fields:
        initiative.comment = payload.comment or ""
    if "tags" in fields:
        configured_tags = {
            row.name.casefold(): row.name
            for row in (
                await session.scalars(
                    select(PiCycleTag).where(PiCycleTag.cycle_id == cycle.id)
                )
            ).all()
        }
        normalized_tags: list[str] = []
        for value in payload.tags or []:
            canonical = configured_tags.get(value.strip().casefold())
            if canonical is None:
                raise ValueError(f"Тэг не настроен для данного PI-цикла: {value}")
            if canonical not in normalized_tags:
                normalized_tags.append(canonical)
        initiative.tags = normalized_tags
    if "effort_by_competency" in fields:
        primary_executor = min(
            initiative.executors,
            key=lambda row: (row.sort_order, str(row.id)),
            default=None,
        )
        if primary_executor is None:
            raise ValueError("У инициативы нет команды-исполнителя")
        competencies, _ = await _initiative_board_context(session, cycle, initiative)
        primary_executor.effort_by_competency = normalized_effort(
            payload.effort_by_competency or {},
            competencies,
            f"Инициатива {initiative.issue_key}",
        )
    if "agreed" in fields:
        initiative.agreed = bool(payload.agreed)
        if initiative.agreed:
            if approved_by:
                initiative.approved_by = approved_by
            initiative.approved_at = datetime.now(timezone.utc)
        else:
            initiative.approved_by = None
            initiative.approved_at = None
    if "sprint_index" in fields or "week_index" in fields:
        sprint_index = payload.sprint_index if "sprint_index" in fields else initiative.sprint_index
        week_index = payload.week_index if "week_index" in fields else initiative.week_index
        validate_sprint_position(cycle, sprint_index, week_index, f"Инициатива {initiative.issue_key}")
        initiative.sprint_index = sprint_index
        initiative.week_index = week_index
    if "board_sort_order" in fields:
        initiative.board_sort_order = int(payload.board_sort_order or 0)
    cycle.boards_initialized = True
    await session.commit()
    return await read_team_boards(session, cycle)


async def create_board_story(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    payload: TeamBoardStoryCreate,
) -> TeamBoardsRead:
    initiative = await _initiative_for_command(session, cycle, initiative_id)
    competencies, _ = await _initiative_board_context(session, cycle, initiative)
    uid = payload.client_uid.strip()
    await _assert_client_uid_available(session, cycle, Story, uid)
    validate_sprint_position(cycle, payload.sprint_index, payload.week_index, f"История {uid}")
    story = Story(
        id=uuid.uuid4(),
        initiative_id=initiative.id,
        client_uid=uid,
        external_key=payload.external_key.strip(),
        title=payload.title.strip(),
        effort_by_competency=normalized_effort(
            payload.effort_by_competency, competencies, f"История {uid}"
        ),
        sprint_index=payload.sprint_index,
        week_index=payload.week_index,
        sort_order=payload.sort_order,
        board_sort_order=payload.board_sort_order,
    )
    session.add(story)
    cycle.boards_initialized = True
    await session.commit()
    return await read_team_boards(session, cycle)


async def update_board_story(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    story_id: uuid.UUID,
    payload: TeamBoardStoryUpdate,
) -> TeamBoardsRead:
    initiative = await _initiative_for_command(session, cycle, initiative_id)
    story = next((row for row in initiative.stories if row.id == story_id), None)
    if story is None:
        raise ValueError("История не найдена для этой инициативы")
    competencies, _ = await _initiative_board_context(session, cycle, initiative)
    fields = payload.model_fields_set
    if "external_key" in fields:
        story.external_key = (payload.external_key or "").strip()
    if "title" in fields:
        story.title = (payload.title or "").strip()
    if "effort_by_competency" in fields:
        story.effort_by_competency = normalized_effort(
            payload.effort_by_competency or {}, competencies, f"История {story.client_uid}"
        )
    if "sprint_index" in fields or "week_index" in fields:
        sprint_index = payload.sprint_index if "sprint_index" in fields else story.sprint_index
        week_index = payload.week_index if "week_index" in fields else story.week_index
        validate_sprint_position(cycle, sprint_index, week_index, f"История {story.client_uid}")
        story.sprint_index = sprint_index
        story.week_index = week_index
    if "sort_order" in fields:
        story.sort_order = int(payload.sort_order or 0)
    if "board_sort_order" in fields:
        story.board_sort_order = int(payload.board_sort_order or 0)
    await session.commit()
    return await read_team_boards(session, cycle)


async def delete_board_story(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    story_id: uuid.UUID,
    payload: TeamBoardDeleteCommand,
) -> TeamBoardsRead:
    initiative = await _initiative_for_command(session, cycle, initiative_id)
    story = next((row for row in initiative.stories if row.id == story_id), None)
    if story is None:
        raise ValueError("История не найдена для этой инициативы")
    children = [row for row in initiative.work_items if row.story_id == story.id]
    affected = [
        {"kind": "work_item", "id": str(row.id), "label": row.client_uid}
        for row in children
    ]
    if affected and not payload.confirm_cascade:
        raise TeamBoardCascadeRequired(
            "Удаление истории также удалит её задачи и связи на доске",
            affected,
        )
    await session.delete(story)
    await session.flush()
    await delete_dangling_connections(session, cycle.id)
    await session.commit()
    return await read_team_boards(session, cycle)


async def _story_by_client_uid(
    initiative: Initiative,
    value: str | None,
) -> Story | None:
    if not value:
        return None
    story = next(
        (row for row in initiative.stories if row.client_uid.casefold() == value.strip().casefold()),
        None,
    )
    if story is None:
        raise ValueError(f"UID истории не найден для задачи: {value}")
    return story


async def create_board_work_item(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    payload: TeamBoardWorkItemCreate,
) -> TeamBoardsRead:
    initiative = await _initiative_for_command(session, cycle, initiative_id)
    competencies, roster = await _initiative_board_context(session, cycle, initiative)
    uid = payload.client_uid.strip()
    await _assert_client_uid_available(session, cycle, WorkItem, uid)
    competency = payload.competency.strip().upper()
    if competency not in competencies:
        raise ValueError(f"Задача {uid}: компетенция не настроена: {competency}")
    assignee_id, assignee = _resolve_assignee(
        uid,
        payload.assignee_member_id,
        payload.assignee_name.strip(),
        competency,
        roster,
    )
    story = await _story_by_client_uid(initiative, payload.story_client_uid)
    validate_sprint_position(cycle, payload.sprint_index, payload.week_index, f"Задача {uid}")
    session.add(
        WorkItem(
            id=uuid.uuid4(),
            initiative_id=initiative.id,
            story_id=story.id if story else None,
            assignee_member_id=assignee_id,
            client_uid=uid,
            assignee_name=assignee,
            competency=competency,
            effort=float(payload.effort),
            sprint_index=payload.sprint_index,
            week_index=payload.week_index,
            sort_order=payload.sort_order,
            board_sort_order=payload.board_sort_order,
        )
    )
    cycle.boards_initialized = True
    await session.commit()
    return await read_team_boards(session, cycle)


async def update_board_work_item(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    work_item_id: uuid.UUID,
    payload: TeamBoardWorkItemUpdate,
) -> TeamBoardsRead:
    initiative = await _initiative_for_command(session, cycle, initiative_id)
    item = next((row for row in initiative.work_items if row.id == work_item_id), None)
    if item is None:
        raise ValueError("Задача не найдена для этой инициативы")
    competencies, roster = await _initiative_board_context(session, cycle, initiative)
    fields = payload.model_fields_set
    competency = (
        (payload.competency or "").strip().upper()
        if "competency" in fields
        else item.competency
    )
    if competency not in competencies:
        raise ValueError(
            f"Задача {item.client_uid}: компетенция не настроена: {competency}"
        )
    assignee = (
        (payload.assignee_name or "").strip()
        if "assignee_name" in fields
        else item.assignee_name
    )
    member_id = (
        payload.assignee_member_id
        if "assignee_member_id" in fields
        else item.assignee_member_id
    )
    member_id, assignee = _resolve_assignee(
        item.client_uid, member_id, assignee, competency, roster
    )
    if "story_client_uid" in fields:
        story = await _story_by_client_uid(initiative, payload.story_client_uid)
        item.story_id = story.id if story else None
    item.competency = competency
    item.assignee_member_id = member_id
    item.assignee_name = assignee
    if "effort" in fields:
        item.effort = float(payload.effort or 0)
    if "sprint_index" in fields or "week_index" in fields:
        sprint_index = payload.sprint_index if "sprint_index" in fields else item.sprint_index
        week_index = payload.week_index if "week_index" in fields else item.week_index
        validate_sprint_position(cycle, sprint_index, week_index, f"Задача {item.client_uid}")
        item.sprint_index = sprint_index
        item.week_index = week_index
    if "sort_order" in fields:
        item.sort_order = int(payload.sort_order or 0)
    if "board_sort_order" in fields:
        item.board_sort_order = int(payload.board_sort_order or 0)
    await session.commit()
    return await read_team_boards(session, cycle)


async def delete_board_work_item(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID,
    work_item_id: uuid.UUID,
    payload: TeamBoardDeleteCommand,
) -> TeamBoardsRead:
    initiative = await _initiative_for_command(session, cycle, initiative_id)
    item = next((row for row in initiative.work_items if row.id == work_item_id), None)
    if item is None:
        raise ValueError("Задача не найдена для этой инициативы")
    connections = list(
        (
            await session.scalars(
                select(BoardConnection).where(
                    BoardConnection.cycle_id == cycle.id,
                    or_(
                        BoardConnection.source_id == item.id,
                        BoardConnection.target_id == item.id,
                    ),
                )
            )
        ).all()
    )
    if connections and not payload.confirm_cascade:
        raise TeamBoardCascadeRequired(
            "Удаление задачи также удалит её связи в Program Board",
            [
                {"kind": "connection", "id": str(row.id), "label": row.client_uid}
                for row in connections
            ],
        )
    await session.delete(item)
    await session.flush()
    await delete_dangling_connections(session, cycle.id)
    await session.commit()
    return await read_team_boards(session, cycle)
