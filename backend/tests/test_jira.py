from auth_fixtures import TEST_SERVICE_PASSWORD

import uuid

import httpx
import pytest

from app.core.config import Settings
from app.schemas.backlog import BacklogTeamRef
from app.schemas.jira import JiraBacklogImportCommand
from app.services.jira import (
    JIRA_FIELDS,
    JiraAccessDenied,
    JiraClient,
    JiraIssueNotFound,
    JiraUnavailable,
    empty_backlog_command,
    jira_issue_to_backlog_command,
    parse_jira_issue,
)


def jira_payload() -> dict:
    return {
        "id": "280221",
        "key": "TECHNOLOGY-15377",
        "fields": {
            "summary": "2024",
            "customfield_15100": 57600,
            "customfield_15114": 115200,
            "customfield_15103": 28800,
            "customfield_14400": ["Discovery (CMDB-6881)"],
            "customfield_15115": 144000,
            "customfield_15104": 662400,
            "customfield_15112": 57600,
            "customfield_15113": 86400,
            "customfield_14403": ["IBM (CMDB-6063)"],
            "customfield_14401": ["DSA (CMDB-6038)"],
            "customfield_15116": 172800,
            "customfield_14402": ["Service (CMDB-12882)"],
            "timetracking": {
                "originalEstimateSeconds": 79200,
                "remainingEstimateSeconds": 79200,
                "timeSpentSeconds": 75600,
            },
            "customfield_12403": {
                "value": "Технологическая компонента",
                "id": "39324",
                "disabled": False,
            },
            "customfield_13902": ["ORG-24"],
            "customfield_13901": ["ORG-24"],
        },
    }


def test_parse_ift_jira_response_and_convert_seconds_to_person_days():
    issue = parse_jira_issue(jira_payload())

    assert issue.issue_key == "TECHNOLOGY-15377"
    assert issue.title == "2024"
    assert issue.original_estimate_days == 2.75
    assert issue.refined_estimate_days == 23.0
    assert issue.effort_by_work_type == {
        "Проектирование": 2.0,
        "Анализ": 1.0,
        "Дизайн": 5.0,
        "Разработка": 2.0,
        "Тестирование": 3.0,
        "ПСИ": 4.0,
        "Другое": 6.0,
    }
    assert issue.effort_by_competency == {"SA": 3.0, "DES": 5.0, "DEV": 8.0, "QA": 7.0}
    assert sum(issue.effort_by_competency.values()) == issue.refined_estimate_days
    assert issue.user_products == ["Discovery (CMDB-6881)"]
    assert issue.channels == ["DSA (CMDB-6038)"]
    assert issue.services == ["Service (CMDB-12882)"]
    assert issue.infrastructures == ["IBM (CMDB-6063)"]
    assert issue.owner_teams == ["ORG-24"]
    assert issue.executor_teams == ["ORG-24"]
    assert issue.initiative_type == "Технологическая компонента"


def test_build_backlog_command_matches_teams_and_preserves_jira_business_fields():
    issue = parse_jira_issue(jira_payload())
    team = BacklogTeamRef(
        id=uuid.uuid4(),
        tribe_id=uuid.uuid4(),
        tribe="Технологии",
        name="ORG-24",
        competencies=["SA", "DEV", "QA", "DES"],
    )
    source = JiraBacklogImportCommand(
        issue_key=issue.issue_key,
        tribe="Технологии",
        fallback_team="ORG-24",
        expected_version=4,
    )

    command, warnings = jira_issue_to_backlog_command(issue, source, [team])

    assert warnings == []
    assert command.title == "2024"
    assert command.product == "Discovery (CMDB-6881)"
    assert command.owner_team == "ORG-24"
    assert command.initiative_type == "Технологическая компонента"
    assert command.systems == [
        "DSA (CMDB-6038)",
        "Service (CMDB-12882)",
        "IBM (CMDB-6063)",
    ]
    assert command.executors[0].team == "ORG-24"
    assert command.executors[0].effort_by_competency == issue.effort_by_competency
    assert command.expected_version == 4


def test_import_warns_when_cycle_team_does_not_have_a_jira_competency():
    issue = parse_jira_issue(jira_payload())
    team = BacklogTeamRef(
        id=uuid.uuid4(),
        tribe_id=uuid.uuid4(),
        tribe="Технологии",
        name="ORG-24",
        competencies=["SA", "DEV", "QA"],
    )
    source = JiraBacklogImportCommand(
        issue_key=issue.issue_key,
        tribe="Технологии",
        fallback_team="ORG-24",
        expected_version=0,
    )

    command, warnings = jira_issue_to_backlog_command(issue, source, [team])

    assert command.executors[0].effort_by_competency == {"SA": 3.0, "DEV": 8.0, "QA": 7.0}
    assert warnings == ["Оценки Jira не перенесены для отсутствующих компетенций: DES"]


def test_build_empty_backlog_command_keeps_entered_issue_and_selected_team():
    source = JiraBacklogImportCommand(
        issue_key="  FALLBACK-42  ",
        tribe="Технологии",
        fallback_team=" ORG-24 ",
        expected_version=7,
    )

    command = empty_backlog_command("FALLBACK-42", source)

    assert command.issue_key == "FALLBACK-42"
    assert command.tribe == "Технологии"
    assert command.owner_team == "ORG-24"
    assert command.title == ""
    assert command.executors[0].team == "ORG-24"
    assert command.executors[0].effort_by_competency == {}
    assert command.expected_version == 7


@pytest.mark.asyncio
async def test_jira_client_uses_basic_auth_api_v2_and_explicit_fields():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json=jira_payload())

    settings = Settings(
        jira_enabled=True,
        jira_base_url="https://jira.example.test/jira/",
        jira_username="service-user",
        jira_password=TEST_SERVICE_PASSWORD,
        _env_file=None,
    )
    issue = await JiraClient(settings, transport=httpx.MockTransport(handler)).get_issue(
        "TECHNOLOGY-15377"
    )

    assert issue.issue_key == "TECHNOLOGY-15377"
    assert captured["url"].startswith(
        "https://jira.example.test/jira/rest/api/2/issue/TECHNOLOGY-15377?fields="
    )
    assert all(field in captured["url"] for field in JIRA_FIELDS)
    assert captured["authorization"].startswith("Basic ")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (404, JiraIssueNotFound),
        (401, JiraAccessDenied),
        (403, JiraAccessDenied),
        (408, JiraUnavailable),
        (429, JiraUnavailable),
        (503, JiraUnavailable),
    ],
)
async def test_jira_client_maps_upstream_errors(status_code, error_type):
    settings = Settings(
        jira_enabled=True,
        jira_base_url="https://jira.example.test/jira",
        jira_username="service-user",
        jira_password=TEST_SERVICE_PASSWORD,
        _env_file=None,
    )
    transport = httpx.MockTransport(lambda _request: httpx.Response(status_code))

    with pytest.raises(error_type):
        await JiraClient(settings, transport=transport).get_issue("TECHNOLOGY-15377")
