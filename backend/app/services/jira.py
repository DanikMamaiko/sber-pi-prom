from __future__ import annotations

import asyncio
import logging
import math
import ssl
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.schemas.backlog import (
    BacklogBoardExecutor,
    BacklogBoardItemRead,
    BacklogItemCommand,
    BacklogTeamRef,
)
from app.schemas.jira import JiraBacklogImportCommand, JiraIssueRead


logger = logging.getLogger("sberpi.jira")


JIRA_FIELDS: tuple[str, ...] = (
    "summary",
    "timetracking",
    "customfield_15103",  # Анализ
    "customfield_15115",  # Дизайн
    "customfield_15116",  # Другое
    "customfield_14403",  # Инфраструктура
    "customfield_14401",  # Канал
    "customfield_13902",  # Команда-владелец
    "customfield_13901",  # Команда-исполнитель
    "customfield_14400",  # Пользовательский продукт
    "customfield_15100",  # Проектирование
    "customfield_15114",  # ПСИ
    "customfield_15112",  # Разработка
    "customfield_14402",  # Сервис
    "customfield_15113",  # Тестирование
    "customfield_12403",  # Тип инициативы
    "customfield_15104",  # Уточнённая оценка
)

WORK_TYPE_FIELDS: tuple[tuple[str, str], ...] = (
    ("Проектирование", "customfield_15100"),
    ("Анализ", "customfield_15103"),
    ("Дизайн", "customfield_15115"),
    ("Разработка", "customfield_15112"),
    ("Тестирование", "customfield_15113"),
    ("ПСИ", "customfield_15114"),
    ("Другое", "customfield_15116"),
)

COMPETENCY_WORK_TYPES: dict[str, tuple[str, ...]] = {
    "SA": ("Проектирование", "Анализ"),
    "DES": ("Дизайн",),
    "DEV": ("Разработка", "Другое"),
    "QA": ("Тестирование", "ПСИ"),
}


class JiraError(RuntimeError):
    pass


class JiraNotConfigured(JiraError):
    pass


class JiraIssueNotFound(JiraError):
    pass


class JiraAccessDenied(JiraError):
    pass


class JiraUnavailable(JiraError):
    pass


class JiraInvalidResponse(JiraError):
    pass


class JiraCapacityExceeded(JiraError):
    def __init__(self, message: str, retry_after_seconds: int):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class JiraRequestLimiter:
    """Process-wide concurrency limit with a bounded, expiring wait queue."""

    def __init__(
        self,
        *,
        max_concurrent: int,
        max_queue_size: int,
        queue_timeout_seconds: float,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self.queue_timeout_seconds = queue_timeout_seconds
        self.retry_after_seconds = max(1, math.ceil(queue_timeout_seconds))
        self._condition = asyncio.Condition()
        self._active = 0
        self._waiting = 0

    @property
    def active_count(self) -> int:
        return self._active

    @property
    def waiting_count(self) -> int:
        return self._waiting

    def _capacity_error(self, reason: str) -> JiraCapacityExceeded:
        logger.warning(
            "jira_request_rejected reason=%s active=%s waiting=%s "
            "max_concurrent=%s max_queue_size=%s",
            reason,
            self._active,
            self._waiting,
            self.max_concurrent,
            self.max_queue_size,
        )
        return JiraCapacityExceeded(
            "Лимит обращений к Jira исчерпан, повторите запрос позже",
            retry_after_seconds=self.retry_after_seconds,
        )

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._condition:
            if self._active >= self.max_concurrent:
                if self._waiting >= self.max_queue_size:
                    raise self._capacity_error("queue_full")
                self._waiting += 1
                try:
                    try:
                        await asyncio.wait_for(
                            self._condition.wait_for(
                                lambda: self._active < self.max_concurrent
                            ),
                            timeout=self.queue_timeout_seconds,
                        )
                    except TimeoutError as error:
                        raise self._capacity_error("queue_timeout") from error
                finally:
                    self._waiting -= 1
            self._active += 1

        try:
            yield
        finally:
            async with self._condition:
                self._active -= 1
                self._condition.notify(1)


def _seconds_to_days(value: Any, workday_hours: float) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return round(seconds / (workday_hours * 3600), 3)


def _display_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    for key in ("value", "name", "label", "key"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _display_values(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else ([] if value is None else [value])
    result: list[str] = []
    for row in rows:
        display = _display_value(row)
        if display and display not in result:
            result.append(display)
    return result


def parse_jira_issue(payload: Any, workday_hours: float = 8.0) -> JiraIssueRead:
    if not isinstance(payload, dict) or not isinstance(payload.get("fields"), dict):
        raise JiraInvalidResponse("Jira вернула ответ без объекта fields")
    fields = payload["fields"]
    issue_key = str(payload.get("key") or "").strip()
    if not issue_key:
        raise JiraInvalidResponse("Jira вернула ответ без ключа Issue")

    efforts: dict[str, float] = {}
    for label, field_id in WORK_TYPE_FIELDS:
        days = _seconds_to_days(fields.get(field_id), workday_hours)
        if days is not None:
            efforts[label] = days
    competency_efforts = {
        competency: round(sum(efforts.get(label, 0.0) for label in labels), 3)
        for competency, labels in COMPETENCY_WORK_TYPES.items()
    }
    competency_efforts = {key: value for key, value in competency_efforts.items() if value}

    timetracking = fields.get("timetracking")
    if not isinstance(timetracking, dict):
        timetracking = {}
    return JiraIssueRead(
        issue_key=issue_key,
        title=str(fields.get("summary") or "").strip(),
        user_products=_display_values(fields.get("customfield_14400")),
        channels=_display_values(fields.get("customfield_14401")),
        services=_display_values(fields.get("customfield_14402")),
        infrastructures=_display_values(fields.get("customfield_14403")),
        owner_teams=_display_values(fields.get("customfield_13902")),
        executor_teams=_display_values(fields.get("customfield_13901")),
        initiative_type=_display_value(fields.get("customfield_12403")),
        original_estimate_days=_seconds_to_days(
            timetracking.get("originalEstimateSeconds"), workday_hours
        ),
        refined_estimate_days=_seconds_to_days(fields.get("customfield_15104"), workday_hours),
        effort_by_work_type=efforts,
        effort_by_competency=competency_efforts,
        synced_at=datetime.now(timezone.utc).isoformat(),
    )


def _normal(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _aliases(value: str) -> set[str]:
    result = {_normal(value)}
    text = value.strip()
    if text.endswith(")") and "(" in text:
        prefix, suffix = text.rsplit("(", 1)
        result.add(_normal(prefix))
        result.add(_normal(suffix[:-1]))
    return {row for row in result if row}


def _match_team(
    jira_values: list[str], teams: list[BacklogTeamRef]
) -> BacklogTeamRef | None:
    wanted: set[str] = set()
    for value in jira_values:
        wanted.update(_aliases(value))
    return next((team for team in teams if _normal(team.name) in wanted), None)


def _join_limited(values: list[str], max_length: int) -> str:
    return ", ".join(values)[:max_length].rstrip(" ,")


def _jira_systems(issue: JiraIssueRead) -> list[str]:
    systems: list[str] = []
    for value in [*issue.channels, *issue.services, *issue.infrastructures]:
        if value not in systems:
            systems.append(value)
    return systems


def _jira_effort_for_executor(
    issue: JiraIssueRead,
    executor: BacklogTeamRef | None,
) -> tuple[dict[str, float], list[str]]:
    warnings: list[str] = []
    effort_by_competency: dict[str, float] = {}
    if executor is not None:
        allowed = {value.upper() for value in executor.competencies}
        effort_by_competency = {
            key: value
            for key, value in issue.effort_by_competency.items()
            if key in allowed and value
        }
        omitted = sorted(
            key for key, value in issue.effort_by_competency.items() if value and key not in allowed
        )
        if omitted:
            warnings.append(
                "Оценки Jira не перенесены для отсутствующих компетенций: " + ", ".join(omitted)
            )
    elif issue.effort_by_competency:
        warnings.append("Оценки Jira не перенесены: команда для ресурсной строки не определена")
    return effort_by_competency, warnings


def jira_issue_to_backlog_command(
    issue: JiraIssueRead,
    source: JiraBacklogImportCommand,
    teams: list[BacklogTeamRef],
) -> tuple[BacklogItemCommand, list[str]]:
    warnings: list[str] = []
    tribe_teams = [team for team in teams if _normal(team.tribe) == _normal(source.tribe)]
    fallback = _match_team([source.fallback_team], tribe_teams) if source.fallback_team else None
    owner = _match_team(issue.owner_teams, tribe_teams)
    if owner is None:
        owner = fallback
        if issue.owner_teams:
            warnings.append("Команда-владелец Jira не найдена в выбранном трайбе")
    executor = _match_team(issue.executor_teams, teams)
    if executor is None:
        executor = fallback or owner
        if issue.executor_teams:
            warnings.append("Команда-исполнитель Jira не найдена в активном PI-цикле")

    effort_by_competency, effort_warnings = _jira_effort_for_executor(issue, executor)
    warnings.extend(effort_warnings)

    return (
        BacklogItemCommand(
            tribe=source.tribe,
            issue_key=issue.issue_key,
            title=issue.title,
            description="",
            product=_join_limited(issue.user_products, 180),
            owner_team=owner.name if owner else "",
            initiative_type=issue.initiative_type[:120],
            target_year=None,
            target_quarter=None,
            customer_priority="",
            team_priority="",
            status="Нет оценки",
            tshirt_size="",
            tags=[],
            systems=_jira_systems(issue),
            executors=(
                [
                    BacklogBoardExecutor(
                        team=executor.name,
                        effort_by_competency=effort_by_competency,
                    )
                ]
                if executor
                else []
            ),
            expected_version=source.expected_version,
        ),
        warnings,
    )


def jira_issue_to_backlog_refresh_command(
    issue: JiraIssueRead,
    current: BacklogBoardItemRead,
    teams: list[BacklogTeamRef],
    expected_version: int,
) -> tuple[BacklogItemCommand, list[str], list[str]]:
    """Merge Jira-owned fields into an existing backlog item.

    SberPI-owned planning fields stay unchanged. If a Jira team cannot be
    resolved in the active PI cycle, keep the current team instead of silently
    clearing it and return the same mapping warning used during import.
    """
    warnings: list[str] = []
    tribe_teams = [team for team in teams if _normal(team.tribe) == _normal(current.tribe)]

    owner = _match_team(issue.owner_teams, tribe_teams)
    if owner is None:
        owner = _match_team([current.owner_team], tribe_teams) if current.owner_team else None
        if issue.owner_teams:
            warnings.append("Команда-владелец Jira не найдена в выбранном трайбе")

    current_executor = current.executors[0] if current.executors else None
    matched_executor = _match_team(issue.executor_teams, teams)
    executor = matched_executor
    if executor is None and current_executor is not None:
        executor = _match_team([current_executor.team], teams)
    if executor is None and current_executor is None:
        executor = owner
    if matched_executor is None and issue.executor_teams:
        warnings.append("Команда-исполнитель Jira не найдена в активном PI-цикле")

    effort_by_competency, effort_warnings = _jira_effort_for_executor(issue, executor)
    warnings.extend(effort_warnings)

    executor_rows: list[BacklogBoardExecutor]
    if executor is not None:
        current_id = (
            current_executor.id
            if current_executor is not None
            and _normal(current_executor.team) == _normal(executor.name)
            else None
        )
        executor_rows = [
            BacklogBoardExecutor(
                id=current_id,
                team=executor.name,
                effort_by_competency=effort_by_competency,
            )
        ]
    elif current_executor is not None:
        # Preserve an existing resource row which is outside the selected
        # cycle's reference data; validation will reject the command rather
        # than allowing a refresh to erase it.
        executor_rows = [
            BacklogBoardExecutor(
                id=current_executor.id,
                team=current_executor.team,
                effort_by_competency=dict(current_executor.effort_by_competency),
            )
        ]
    else:
        executor_rows = []

    command = BacklogItemCommand(
        tribe=current.tribe,
        issue_key=current.issue_key,
        title=issue.title,
        description=current.description,
        product=_join_limited(issue.user_products, 180),
        owner_team=owner.name if owner else current.owner_team,
        initiative_type=issue.initiative_type[:120],
        target_year=current.target_year,
        target_quarter=current.target_quarter,
        customer_priority=current.customer_priority,
        team_priority=current.team_priority,
        status=current.status,
        tshirt_size=current.tshirt_size,
        tags=list(current.tags),
        systems=_jira_systems(issue),
        executors=executor_rows,
        expected_version=expected_version,
    )

    updated_fields: list[str] = []
    for field in ("title", "product", "owner_team", "initiative_type", "systems"):
        if getattr(current, field) != getattr(command, field):
            updated_fields.append(field)
    current_team = current_executor.team if current_executor else ""
    next_team = executor_rows[0].team if executor_rows else ""
    if current_team != next_team:
        updated_fields.append("executor_team")
    current_effort = dict(current_executor.effort_by_competency) if current_executor else {}
    next_effort = dict(executor_rows[0].effort_by_competency) if executor_rows else {}
    if current_effort != next_effort:
        updated_fields.append("effort_by_competency")
    return command, warnings, updated_fields


def empty_backlog_command(
    issue_key: str,
    source: JiraBacklogImportCommand,
) -> BacklogItemCommand:
    """Build the minimal initiative used when Jira cannot supply issue data."""
    team = source.fallback_team.strip()
    return BacklogItemCommand(
        tribe=source.tribe,
        issue_key=issue_key,
        owner_team=team,
        executors=(
            [BacklogBoardExecutor(team=team, effort_by_competency={})]
            if team
            else []
        ),
        expected_version=source.expected_version,
    )


class JiraClient:
    def __init__(
        self,
        settings: Settings,
        *,
        limiter: JiraRequestLimiter | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.limiter = limiter
        self.transport = transport

    def _verify(self) -> bool | ssl.SSLContext:
        if not self.settings.jira_verify_ssl:
            return False
        bundle = self.settings.jira_ca_bundle.strip()
        if not bundle:
            return True
        if not Path(bundle).is_file():
            raise JiraNotConfigured(f"Файл JIRA_CA_BUNDLE не найден: {bundle}")
        return ssl.create_default_context(cafile=bundle)

    async def get_issue(self, issue_key: str) -> JiraIssueRead:
        if not self.settings.jira_is_configured:
            raise JiraNotConfigured("Интеграция Jira не настроена")
        url = (
            self.settings.jira_base_url.rstrip("/")
            + "/rest/api/2/issue/"
            + quote(issue_key, safe="")
        )
        async def request_issue() -> httpx.Response:
            async with httpx.AsyncClient(
                auth=httpx.BasicAuth(
                    self.settings.jira_username.strip(), self.settings.jira_password
                ),
                headers={"Accept": "application/json"},
                timeout=self.settings.jira_timeout_seconds,
                verify=self._verify(),
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                return await client.get(url, params={"fields": ",".join(JIRA_FIELDS)})

        try:
            if self.limiter is None:
                response = await request_issue()
            else:
                async with self.limiter.slot():
                    response = await request_issue()
        except httpx.TimeoutException as error:
            raise JiraUnavailable("Jira не ответила за отведённое время") from error
        except httpx.HTTPError as error:
            raise JiraUnavailable("Не удалось подключиться к Jira") from error

        if response.status_code == 404:
            raise JiraIssueNotFound(f"Issue {issue_key} не найден в Jira")
        if response.status_code in {401, 403}:
            raise JiraAccessDenied("Jira отклонила учётные данные или права доступа")
        if response.status_code in {408, 429} or response.status_code >= 500:
            raise JiraUnavailable(f"Jira временно недоступна (HTTP {response.status_code})")
        if response.status_code != 200:
            raise JiraInvalidResponse(f"Jira вернула неожиданный HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise JiraInvalidResponse("Jira вернула ответ не в формате JSON") from error
        return parse_jira_issue(payload, self.settings.jira_workday_hours)
