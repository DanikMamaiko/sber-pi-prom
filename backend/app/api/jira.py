import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas.jira import (
    JiraBacklogImportCommand,
    JiraBacklogImportRead,
    JiraBacklogRefreshCommand,
    JiraBacklogRefreshRead,
)
from app.services.backlog_board import (
    BacklogNotFound,
    create_backlog_item,
    get_backlog_item_issue_key,
    normalize_issue_key,
    read_backlog_board,
    update_backlog_item,
)
from app.services.jira import (
    JiraAccessDenied,
    JiraCapacityExceeded,
    JiraClient,
    JiraInvalidResponse,
    JiraIssueNotFound,
    JiraNotConfigured,
    JiraUnavailable,
    empty_backlog_command,
    jira_issue_to_backlog_command,
    jira_issue_to_backlog_refresh_command,
)
from app.services.optimistic_locking import lock_backlog


router = APIRouter(
    tags=["Jira"],
    dependencies=[Depends(require_permission(Permission.BACKLOG_WRITE))],
)


def get_jira_client(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JiraClient:
    return JiraClient(settings, limiter=request.app.state.jira_limiter)


def _jira_http_error(error: Exception) -> HTTPException:
    if isinstance(error, JiraCapacityExceeded):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(error),
            headers={"Retry-After": str(error.retry_after_seconds)},
        )
    if isinstance(error, JiraIssueNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, JiraNotConfigured):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    if isinstance(error, JiraUnavailable):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    if isinstance(error, JiraAccessDenied):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))


def _jira_fallback_warning(error: Exception) -> str:
    if isinstance(error, JiraIssueNotFound):
        reason = str(error)
    elif isinstance(error, JiraNotConfigured):
        reason = "Jira отключена или не настроена"
    else:
        reason = str(error)
    return f"{reason}. Инициатива создана без данных Jira — заполните поля вручную"


@router.post(
    "/backlog-board/items/from-jira",
    response_model=JiraBacklogImportRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_backlog_item_from_jira(
    payload: JiraBacklogImportCommand,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    jira_client: JiraClient = Depends(get_jira_client),
):
    try:
        issue_key = normalize_issue_key(payload.issue_key)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    jira_issue = None
    fallback_warnings: list[str] = []
    try:
        jira_issue = await jira_client.get_issue(issue_key)
    except JiraCapacityExceeded as error:
        raise _jira_http_error(error) from error
    except (JiraIssueNotFound, JiraNotConfigured, JiraUnavailable) as error:
        fallback_warnings.append(_jira_fallback_warning(error))
    except (JiraAccessDenied, JiraInvalidResponse) as error:
        raise _jira_http_error(error) from error

    # Do not hold a database transaction or row lock while waiting on Jira.
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    try:
        current = await read_backlog_board(session, cycle_id)
        if jira_issue is None:
            command = empty_backlog_command(issue_key, payload)
            warnings = fallback_warnings
        else:
            command, warnings = jira_issue_to_backlog_command(
                jira_issue, payload, current.reference_data.teams
            )
        item = await create_backlog_item(session, command, cycle_id)
        if jira_issue is not None:
            item.jira_issue_data = jira_issue.model_dump(mode="json")
        await session.commit()
        return JiraBacklogImportRead(
            board=await read_backlog_board(session, cycle_id),
            jira=jira_issue,
            warnings=warnings,
        )
    except BacklogNotFound as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/backlog-board/items/{item_id}/refresh-from-jira",
    response_model=JiraBacklogRefreshRead,
)
async def refresh_backlog_item_from_jira(
    item_id: uuid.UUID,
    payload: JiraBacklogRefreshCommand,
    cycle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    jira_client: JiraClient = Depends(get_jira_client),
):
    try:
        issue_key = await get_backlog_item_issue_key(session, item_id)
    except BacklogNotFound as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    # End the read-only transaction before the potentially slow Jira call.
    await session.rollback()
    try:
        jira_issue = await jira_client.get_issue(issue_key)
    except (
        JiraAccessDenied,
        JiraCapacityExceeded,
        JiraInvalidResponse,
        JiraIssueNotFound,
        JiraNotConfigured,
        JiraUnavailable,
    ) as error:
        raise _jira_http_error(error) from error

    # The optimistic lock is acquired only after Jira has answered. A change
    # made while waiting produces 409 and leaves the item untouched.
    if cycle_id is not None:
        await get_cycle_or_404(session, cycle_id)
    await lock_backlog(session, payload.expected_version)
    try:
        current_board = await read_backlog_board(session, cycle_id)
        current_item = next((row for row in current_board.items if row.id == item_id), None)
        if current_item is None:
            raise BacklogNotFound("Элемент бэклога не найден")
        command, warnings, updated_fields = jira_issue_to_backlog_refresh_command(
            jira_issue,
            current_item,
            current_board.reference_data.teams,
            payload.expected_version,
        )
        item = await update_backlog_item(session, item_id, command, cycle_id)
        item.jira_issue_data = jira_issue.model_dump(mode="json")
        await session.commit()
        return JiraBacklogRefreshRead(
            board=await read_backlog_board(session, cycle_id),
            jira=jira_issue,
            warnings=warnings,
            updated_fields=updated_fields,
        )
    except BacklogNotFound as error:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
