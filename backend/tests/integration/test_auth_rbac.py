import pytest


pytestmark = pytest.mark.integration


async def _login(client, username: str, password: str):
    response = await client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response


async def test_navigation_requires_auth_and_exposes_only_minimal_cycles(raw_api_client):
    assert (await raw_api_client.get("/app/navigation")).status_code == 401
    await _login(raw_api_client, "admin", "admin123")
    created = await raw_api_client.post(
        "/pi-cycles",
        json={"year": 2038, "quarter": "Q2", "start_date": "2038-04-01", "sprint_count": 6},
    )
    assert created.status_code == 201, created.text

    response = await raw_api_client.get("/app/navigation")

    assert response.status_code == 200
    body = response.json()
    assert body["sections"][0] == {
        "id": "budget",
        "name": "Бюджетирование",
        "enabled": False,
        "status": "development",
        "message": "Находится в разработке. Будет доступно позже.",
    }
    assert body["pi_cycles"] == [
        {"id": created.json()["id"], "year": 2038, "quarter": "Q2"}
    ]
    assert set(body["pi_cycles"][0]) == {"id", "year", "quarter"}
    assert [tab["id"] for tab in body["tabs"]] == [
        "data",
        "backlog",
        "prep",
        "goals",
        "teams",
        "pb",
        "risks",
    ]


@pytest.mark.parametrize(
    ("username", "password", "expected_tabs", "writable_tabs"),
    (
        (
            "editor",
            "editor123",
            ["backlog", "prep", "goals", "teams", "pb", "risks"],
            {"backlog", "prep", "teams", "pb", "risks"},
        ),
        (
            "pm",
            "pm123",
            ["backlog", "prep", "goals", "teams", "pb", "risks"],
            {"prep"},
        ),
        (
            "user",
            "user123",
            ["backlog", "prep", "goals", "teams", "pb", "risks"],
            set(),
        ),
    ),
)
async def test_navigation_matches_role_matrix(
    raw_api_client,
    username,
    password,
    expected_tabs,
    writable_tabs,
):
    await _login(raw_api_client, username, password)

    response = await raw_api_client.get("/app/navigation")

    assert response.status_code == 200
    tabs = response.json()["tabs"]
    assert [tab["id"] for tab in tabs] == expected_tabs
    assert {tab["id"] for tab in tabs if tab["can_write"]} == writable_tabs
    assert {tab["id"] for tab in tabs if tab["can_approve"]} == (
        {"teams"} if username == "editor" else set()
    )


@pytest.mark.parametrize(
    ("username", "password", "year"),
    (
        ("admin", "admin123", 2041),
        ("editor", "editor123", 2042),
        ("pm", "pm123", 2043),
        ("user", "user123", 2044),
    ),
)
async def test_every_role_can_select_and_initialize_any_quarter(
    raw_api_client,
    username,
    password,
    year,
):
    await _login(raw_api_client, username, password)

    first = await raw_api_client.post(
        "/app/pi-cycles",
        json={"year": year, "quarter": "Q4"},
    )
    repeated = await raw_api_client.post(
        "/app/pi-cycles",
        json={"year": year, "quarter": "Q4"},
    )

    assert first.status_code == 200, first.text
    assert repeated.status_code == 200, repeated.text
    assert first.json() == repeated.json()
    assert first.json()["year"] == year
    assert first.json()["quarter"] == "Q4"


async def test_select_cycle_requires_authentication(raw_api_client):
    response = await raw_api_client.post(
        "/app/pi-cycles",
        json={"year": 2045, "quarter": "Q1"},
    )

    assert response.status_code == 401


async def test_pm_can_read_backlog_and_edit_pre_pi_but_not_pi_data(raw_api_client):
    await _login(raw_api_client, "pm", "pm123")

    # PM получил доступ на просмотр «Бэклога команд».
    assert (await raw_api_client.get("/backlog-board")).status_code == 200
    # Данные PI-цикла по-прежнему недоступны PM (нет pi_data:read) — заодно
    # подтверждаем, что 403-механизм для запрещённых ресурсов продолжает работать.
    assert (await raw_api_client.get("/pi-cycles")).status_code == 403

    # PRE PI теперь редактируем: создаём цикл, читаем актуальную версию и
    # заменяем pre-pi (раньше этот PUT возвращал 403).
    cycle = await raw_api_client.post(
        "/app/pi-cycles",
        json={"year": 2051, "quarter": "Q4"},
    )
    assert cycle.status_code == 200, cycle.text
    cycle_id = cycle.json()["id"]

    current = await raw_api_client.get(f"/pi-cycles/{cycle_id}/pre-pi")
    assert current.status_code == 200, current.text
    expected_version = current.json()["version"]

    write = await raw_api_client.put(
        f"/pi-cycles/{cycle_id}/pre-pi",
        json={"initiatives": [], "expected_version": expected_version},
    )
    assert write.status_code == 200, write.text
