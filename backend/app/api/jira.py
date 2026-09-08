import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._common import get_cycle_or_404
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas.jira import JiraBacklogImportCommand, JiraBacklogImportRead
from app.services.backlog_board import (
    BacklogNotFound,
    create_backlog_item,
    normalize_issue_key,
    read_backlog_board,
)
from app.services.jira import (
    JiraAccessDenied,
    JiraClient,
    JiraInvalidResponse,
    JiraIssueNotFound,
    JiraNotConfigured,
    JiraUnavailable,
    empty_backlog_command,
    jira_issue_to_backlog_command,
)
from app.services.optimistic_locking import lock_backlog


router = APIRouter(
    tags=["Jira"],
    dependencies=[Depends(require_permission(Permission.BACKLOG_WRITE))],
)


def get_jira_client(settings: Settings = Depends(get_settings)) -> JiraClient:
    return JiraClient(settings)


def _jira_http_error(error: Exception) -> HTTPException:
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
