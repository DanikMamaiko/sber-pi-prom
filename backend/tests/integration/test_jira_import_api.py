import pytest

from app.api.jira import get_jira_client
from app.main import app
from app.schemas.jira import JiraIssueRead


pytestmark = pytest.mark.integration


class StubJiraClient:
    async def get_issue(self, issue_key: str) -> JiraIssueRead:
        assert issue_key == "TECHNOLOGY-15377"
        return JiraIssueRead(
            issue_key=issue_key,
            title="Инициатива из Jira",
            user_products=["SberPI (CMDB-1)"],
            channels=["Web (CMDB-2)"],
            services=["Planning (CMDB-3)"],
            infrastructures=["Platform (CMDB-4)"],
            owner_teams=["Команда Альфа"],
            executor_teams=["Команда Альфа"],
            initiative_type="Развитие функционала",
            original_estimate_days=10,
            refined_estimate_days=23,
            effort_by_work_type={"Анализ": 3, "Разработка": 13, "Тестирование": 7},
            effort_by_competency={"SA": 3, "DEV": 13, "QA": 7},
            synced_at="2026-09-08T10:00:00+00:00",
        )


def assert_ok(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()


@pytest.mark.asyncio
async def test_import_from_jira_creates_versioned_backlog_item_and_persists_snapshot(api_client):
    cycle = assert_ok(
        await api_client.post(
            "/pi-cycles", json={"year": 2028, "quarter": "Q3", "sprint_count": 3}
        ),
        201,
    )
    assert_ok(
        await api_client.put(
            f"/pi-cycles/{cycle['id']}/setup",
            json={
                "start_date": "2028-07-03",
                "sprint_count": 3,
                "pirs": [],
                "teams": [
                    {
                        "tribe": "Регрессия",
                        "name": "Команда Альфа",
                        "team_type": "Agile",
                        "competencies": ["SA", "DEV", "QA", "DES"],
                    }
                ],
                "goals": [],
                "tags": [],
            },
        )
    )

    app.dependency_overrides[get_jira_client] = lambda: StubJiraClient()
    try:
        imported = assert_ok(
            await api_client.post(
                f"/backlog-board/items/from-jira?cycle_id={cycle['id']}",
                json={
                    "issue_key": "TECHNOLOGY-15377",
                    "tribe": "Регрессия",
                    "fallback_team": "Команда Альфа",
                },
            ),
            201,
        )
    finally:
        app.dependency_overrides.pop(get_jira_client, None)

    assert imported["warnings"] == []
    assert imported["jira"]["refined_estimate_days"] == 23
    item = imported["board"]["items"][0]
    assert item["issue_key"] == "TECHNOLOGY-15377"
    assert item["title"] == "Инициатива из Jira"
    assert item["product"] == "SberPI (CMDB-1)"
    assert item["owner_team"] == "Команда Альфа"
    assert item["systems"] == ["Web (CMDB-2)", "Planning (CMDB-3)", "Platform (CMDB-4)"]
    assert item["total_effort"] == 23
    assert item["jira"]["original_estimate_days"] == 10
    assert item["jira"]["effort_by_work_type"]["Разработка"] == 13

    persisted = assert_ok(
        await api_client.get(f"/backlog-board?cycle_id={cycle['id']}")
    )["items"][0]
    assert persisted["jira"] == item["jira"]
