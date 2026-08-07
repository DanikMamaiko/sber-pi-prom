from copy import deepcopy

import pytest


pytestmark = pytest.mark.integration


def assert_ok(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()


async def create_cycle_with_setup(client, *, year=2028, quarter="Q4"):
    cycle = assert_ok(
        await client.post(
            "/pi-cycles",
            json={"year": year, "quarter": quarter, "sprint_count": 3},
        ),
        201,
    )
    setup = assert_ok(
        await client.put(
            f"/pi-cycles/{cycle['id']}/setup",
            json={
                "start_date": "2028-10-02",
                "sprint_count": 3,
                "pirs": [{"name": "ПИР E2E", "date": "2028-10-16"}],
                "teams": [
                    {
                        "tribe": "Регрессия",
                        "name": "Команда Альфа",
                        "team_type": "Agile",
                        "competencies": ["SA", "DEV", "QA"],
                    },
                    {
                        "tribe": "Регрессия",
                        "name": "Проект Бета",
                        "team_type": "ИТ-проект",
                        "competencies": ["SA", "DEV"],
                    },
                ],
                "goals": ["Цель регрессии"],
                "tags": ["E2E"],
            },
        )
    )
    return cycle, setup


@pytest.mark.asyncio
async def test_compatibility_snapshot_is_rejected_and_absent_from_read_contract(api_client):
    cycle = assert_ok(
        await api_client.post(
            "/pi-cycles",
            json={"year": 2028, "quarter": "Q1"},
        ),
        201,
    )
    assert "snapshot" not in cycle

    create_with_snapshot = await api_client.post(
        "/pi-cycles",
        json={
            "year": 2028,
            "quarter": "Q2",
            "snapshot": {"legacy": {"value": "must be rejected"}},
        },
    )
    assert create_with_snapshot.status_code == 422

    patch_with_snapshot = await api_client.patch(
        f"/pi-cycles/{cycle['id']}",
        json={"snapshot": {"legacy": {"value": "must be rejected"}}},
    )
    assert patch_with_snapshot.status_code == 422

    persisted = assert_ok(await api_client.get("/pi-cycles"))[0]
    assert "snapshot" not in persisted


@pytest.mark.asyncio
async def test_full_pi_cycle_flow_persists_and_deletes_dependencies(api_client):
    assert assert_ok(await api_client.get("/health")) == {"status": "ok"}
    cycle, setup = await create_cycle_with_setup(api_client)
    cycle_id = cycle["id"]
    assert setup["initialized"] is True
    assert len(setup["teams"]) == 2
    cycle_after_setup = next(
        row for row in assert_ok(await api_client.get("/pi-cycles")) if row["id"] == cycle_id
    )
    assert cycle_after_setup["setup_initialized"] is True
    assert cycle_after_setup["initiatives_initialized"] is False

    # Reopening the same quarter is idempotent and the normalized setup survives.
    duplicate = assert_ok(
        await api_client.post(
            "/pi-cycles",
            json={"year": 2028, "quarter": "Q4", "sprint_count": 9},
        ),
        201,
    )
    assert duplicate["id"] == cycle_id
    assert assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/setup"))["teams"] == setup["teams"]

    teams = assert_ok(await api_client.get("/teams"))
    alpha = next(row for row in teams if row["name"] == "Команда Альфа")

    member = assert_ok(
        await api_client.post(
            "/team-members",
            json={
                "team_id": alpha["id"],
                "full_name": "Иванов Иван",
                "competency": "SA",
                "rate": 1,
            },
        ),
        201,
    )
    assert member["team_id"] == alpha["id"]
    assert any(row["id"] == member["id"] for row in assert_ok(await api_client.get("/team-members")))

    board = assert_ok(
        await api_client.put(
            "/backlog-board",
            json={
                "items": [
                    {
                        "tribe": "Регрессия",
                        "issue_key": "E2E-2028-001",
                        "title": "Регрессионная инициатива",
                        "product": "SberPI",
                        "owner_team": "Команда Альфа",
                        "initiative_type": "Развитие функционала",
                        "target_year": 2028,
                        "target_quarter": "Q4",
                        "customer_priority": "1",
                        "team_priority": "1",
                        "tags": ["E2E"],
                        "systems": ["E2E"],
                        "executors": [
                            {
                                "team": "Команда Альфа",
                                "effort_by_competency": {"SA": 3, "DEV": 5},
                            }
                        ],
                    }
                ]
            },
        )
    )
    backlog_item = board["items"][0]
    assert backlog_item["title"] == "Регрессионная инициатива"
    assert assert_ok(await api_client.get("/backlog-board"))["items"][0]["id"] == backlog_item["id"]

    dispatched = assert_ok(
        await api_client.post(
            "/backlog-board/dispatch",
            json={"tribe": "Регрессия", "target_year": 2028, "target_quarter": "Q4"},
        )
    )
    assert dispatched["items"][0]["status"] == "Отправлена в Pre PI Planning"
    initiative = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))["initiatives"][0]

    invalid_pre_pi = {
        "initiatives": [
            {
                "id": initiative["id"],
                "issue_key": "E2E-2028-001",
                "title": "Регрессионная инициатива",
                "product": "SberPI",
                "owner_team": "Команда Альфа",
                "owner_tribe": "Регрессия",
                "initiative_type": "Развитие функционала",
                "customer_priority": "1",
                "team_priority": "1",
                "status": "planned",
                "pre_planned": True,
                "tags": ["E2E"],
                "executors": [
                    {
                        "team": "Команда Альфа",
                        "tribe": "Регрессия",
                        "effort_by_competency": {"SA": 3, "DEV": 5},
                    }
                ],
            }
        ]
    }
    assert_ok(await api_client.put(f"/pi-cycles/{cycle_id}/pre-pi", json=invalid_pre_pi))
    required_error = await api_client.post(
        f"/pi-cycles/{cycle_id}/pre-pi/submit",
        json={"teams": [{"tribe": "Регрессия", "name": "Команда Альфа"}]},
    )
    assert required_error.status_code == 422
    assert required_error.json()["detail"]["problems"][0]["issue_key"] == "E2E-2028-001"

    valid_pre_pi = deepcopy(invalid_pre_pi)
    valid_row = valid_pre_pi["initiatives"][0]
    valid_row.update(
        {
            "goal_text": "Цель регрессии",
            "metric": "Прохождение E2E",
            "current_value": "0%",
            "target_value": "100%",
            "hypothesis": "Сквозной поток стабилен",
            "redesign": "Не требуется",
            "tags": ["E2E"],
        }
    )
    pre_pi = assert_ok(await api_client.put(f"/pi-cycles/{cycle_id}/pre-pi", json=valid_pre_pi))
    assert pre_pi["initiatives"][0]["goal_text"] == "Цель регрессии"

    submitted = assert_ok(
        await api_client.post(
            f"/pi-cycles/{cycle_id}/pre-pi/submit",
            json={"teams": [{"tribe": "Регрессия", "name": "Команда Альфа"}]},
        )
    )
    assert submitted["goals_added"] == 1
    assert submitted["board_added"] == 1
    repeated = assert_ok(
        await api_client.post(
            f"/pi-cycles/{cycle_id}/pre-pi/submit",
            json={"teams": [{"tribe": "Регрессия", "name": "Команда Альфа"}]},
        )
    )
    assert repeated["goals_added"] == 0
    assert repeated["board_added"] == 0

    goals = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/goals-board"))
    focused_goal = assert_ok(
        await api_client.patch(
            f"/pi-cycles/{cycle_id}/goals-board/goals/{goals['goals'][0]['id']}",
            json={"target_value": "95%"},
        )
    )
    assert focused_goal["goals"][0]["target_value"] == "95%"
    assert assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))["initiatives"][0]["target_value"] == "95%"

    goals = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/goals-board"))
    goals["goals"][0]["target_value"] = "99%"
    edited_goals = assert_ok(
        await api_client.put(
            f"/pi-cycles/{cycle_id}/goals-board",
            json={"goals": goals["goals"]},
        )
    )
    assert edited_goals["goals"][0]["target_value"] == "99%"
    assert assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))["initiatives"][0]["target_value"] == "99%"

    capacity = assert_ok(
        await api_client.put(
            f"/pi-cycles/{cycle_id}/capacity",
            json={
                "teams": [
                    {
                        "tribe": "Регрессия",
                        "team": "Команда Альфа",
                        "members": [
                            {
                                "client_uid": "member-e2e-1",
                                "full_name": "Иванов Иван",
                                "competency": "SA",
                                "rate": 1,
                                "vacation_ranges": [
                                    {"start": "2028-10-02", "end": "2028-10-03"}
                                ],
                                "ceremony_percent": 10,
                                "risk_percent": 5,
                                "efficiency": 0.9,
                            }
                        ],
                    }
                ]
            },
        )
    )
    alpha_capacity = next(row for row in capacity["teams"] if row["team"] == "Команда Альфа")
    assert alpha_capacity["planned_effort"] == 8
    assert alpha_capacity["available_capacity"] > 0

    team_boards = assert_ok(
        await api_client.put(
            f"/pi-cycles/{cycle_id}/team-boards",
            json={
                "initiatives": [
                    {
                        "id": initiative["id"],
                        "issue_key": "E2E-2028-001",
                        "pre_planned": True,
                        "on_board": True,
                        "sprint_index": 0,
                        "week_index": 0,
                        "stories": [
                            {
                                "client_uid": "story-e2e-1",
                                "external_key": "E2E-2028-001-S1",
                                "title": "История E2E",
                                "effort_by_competency": {"SA": 2},
                                "sprint_index": 0,
                                "week_index": 0,
                            }
                        ],
                        "work_items": [
                            {
                                "client_uid": "work-e2e-1",
                                "story_client_uid": "story-e2e-1",
                                "assignee_name": "Иванов Иван",
                                "competency": "SA",
                                "effort": 2,
                                "sprint_index": 0,
                                "week_index": 0,
                            }
                        ],
                    }
                ]
            },
        )
    )
    assert team_boards["initiatives"][0]["stories"][0]["client_uid"] == "story-e2e-1"
    assert team_boards["initiatives"][0]["work_items"][0]["client_uid"] == "work-e2e-1"
    story = team_boards["initiatives"][0]["stories"][0]
    work_item = team_boards["initiatives"][0]["work_items"][0]

    program_board = assert_ok(
        await api_client.put(
            f"/pi-cycles/{cycle_id}/program-board",
            json={
                "connections": [
                    {
                        "client_uid": "connection-e2e-1",
                        "source": {"kind": "c", "ref": "E2E-2028-001"},
                        "target": {"kind": "w", "ref": "work-e2e-1"},
                        "bend": {"dx": 25, "dy": -10},
                    }
                ]
            },
        )
    )
    assert program_board["connections"][0]["bend"] == {"dx": 25.0, "dy": -10.0}
    assert [row["number"] for row in program_board["sprints"]] == [1, 2, 3]
    assert program_board["sprints"][1]["events"][0]["name"] == "ПИР E2E"
    assert program_board["cards"][0]["id"] == initiative["id"]
    assert program_board["cards"][0]["primary_team"] == "Команда Альфа"

    moved = assert_ok(
        await api_client.raw.patch(
            f"/pi-cycles/{cycle_id}/program-board/initiatives/{initiative['id']}/position",
            json={
                "expected_version": program_board["version"],
                "sprint_index": 1,
                "sort_order": 0,
            },
        )
    )
    assert moved["cards"][0]["sprint_index"] == 1
    linked_team_board = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/team-boards"))
    assert linked_team_board["initiatives"][0]["sprint_index"] == 1
    stale_move = await api_client.raw.patch(
        f"/pi-cycles/{cycle_id}/program-board/initiatives/{initiative['id']}/position",
        json={
            "expected_version": program_board["version"],
            "sprint_index": 2,
            "sort_order": 0,
        },
    )
    assert stale_move.status_code == 409
    assert stale_move.json()["detail"]["code"] == "version_conflict"

    connection_id = moved["connections"][0]["id"]
    straight = assert_ok(
        await api_client.raw.patch(
            f"/pi-cycles/{cycle_id}/program-board/connections/{connection_id}",
            json={"expected_version": moved["version"], "clear_bend": True},
        )
    )
    assert straight["connections"][0]["bend"] is None
    deleted_edge = assert_ok(
        await api_client.raw.request(
            "DELETE",
            f"/pi-cycles/{cycle_id}/program-board/connections/{connection_id}",
            json={"expected_version": straight["version"]},
        )
    )
    assert deleted_edge["connections"] == []
    program_board = assert_ok(
        await api_client.raw.post(
            f"/pi-cycles/{cycle_id}/program-board/connections",
            json={
                "expected_version": deleted_edge["version"],
                "source": {"kind": "work_item", "id": work_item["id"]},
                "target": {"kind": "initiative", "id": initiative["id"]},
            },
        ),
        201,
    )
    assert program_board["connections"][0]["client_uid"] == program_board["connections"][0]["id"]
    program_board = assert_ok(
        await api_client.raw.post(
            f"/pi-cycles/{cycle_id}/program-board/connections",
            json={
                "expected_version": program_board["version"],
                "source": {"kind": "initiative", "id": initiative["id"]},
                "target": {"kind": "story", "id": story["id"]},
            },
        ),
        201,
    )
    program_board = assert_ok(
        await api_client.raw.post(
            f"/pi-cycles/{cycle_id}/program-board/connections",
            json={
                "expected_version": program_board["version"],
                "source": {"kind": "story", "id": story["id"]},
                "target": {"kind": "work_item", "id": work_item["id"]},
            },
        ),
        201,
    )
    assert [(row["source"]["kind"], row["target"]["kind"]) for row in program_board["connections"]][-2:] == [
        ("c", "g"),
        ("g", "w"),
    ]

    risks = assert_ok(
        await api_client.put(
            f"/pi-cycles/{cycle_id}/risks-board",
            json={
                "risks": [
                    {
                        "client_uid": "risk-general-e2e",
                        "scope": "general",
                        "description": "Общий риск E2E",
                    },
                    {
                        "client_uid": "risk-team-e2e",
                        "scope": "team",
                        "team": {"tribe": "Регрессия", "name": "Команда Альфа"},
                        "is_shared": True,
                        "description": "Командный риск E2E",
                        "owner": "Иванов Иван",
                    },
                ]
            },
        )
    )
    assert len(risks["risks"]) == 2

    # Page reload/reopen contract: every normalized aggregate is independently readable.
    for suffix in (
        "setup",
        "pre-pi",
        "goals-board",
        "team-boards",
        "capacity",
        "program-board",
        "risks-board",
        "overview",
    ):
        assert (await api_client.get(f"/pi-cycles/{cycle_id}/{suffix}")).status_code == 200
    overview = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/overview"))
    assert overview["teams_count"] == 2
    assert overview["initiatives_count"] == 1

    # Removing a work item removes its now-dangling Program Board connection.
    without_children = deepcopy(team_boards["initiatives"][0])
    without_children["stories"] = []
    without_children["work_items"] = []
    assert_ok(
        await api_client.put(
            f"/pi-cycles/{cycle_id}/team-boards",
            json={"initiatives": [without_children]},
        )
    )
    assert assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/program-board"))["connections"] == []

    # Removing an initiative removes it from goals and all board aggregates.
    assert_ok(await api_client.put(f"/pi-cycles/{cycle_id}/pre-pi", json={"initiatives": []}))
    assert assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/initiatives")) == []
    assert assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/goals-board"))["goals"] == []

    # Removing a team from setup cascades its capacity and team risks, but keeps general risks.
    reduced_setup = deepcopy(setup)
    reduced_setup.pop("initialized", None)
    reduced_setup["teams"] = [row for row in reduced_setup["teams"] if row["name"] == "Проект Бета"]
    assert_ok(await api_client.put(f"/pi-cycles/{cycle_id}/setup", json=reduced_setup))
    remaining_capacity = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/capacity"))
    assert [row["team"] for row in remaining_capacity["teams"]] == ["Проект Бета"]
    remaining_risks = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/risks-board"))
    assert [row["scope"] for row in remaining_risks["risks"]] == ["general"]

    # Another quarter has isolated setup and does not change the reopened Q4 cycle.
    other_cycle = assert_ok(
        await api_client.post(
            "/pi-cycles",
            json={"year": 2028, "quarter": "Q3", "sprint_count": 2},
        ),
        201,
    )
    assert other_cycle["id"] != cycle_id
    q4_setup = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/setup"))
    assert [row["name"] for row in q4_setup["teams"]] == ["Проект Бета"]


@pytest.mark.asyncio
async def test_invalid_aggregate_puts_return_422_and_are_atomic(api_client):
    cycle, _ = await create_cycle_with_setup(api_client)
    cycle_id = cycle["id"]

    board = assert_ok(
        await api_client.put(
            "/backlog-board",
            json={
                "items": [
                    {
                        "tribe": "Регрессия",
                        "issue_key": "E2E-422-001",
                        "title": "Проверка 422",
                        "owner_team": "Команда Альфа",
                        "initiative_type": "Развитие функционала",
                        "target_year": 2028,
                        "target_quarter": "Q4",
                        "executors": [
                            {
                                "team": "Проект Бета",
                                "effort_by_competency": {"DEV": 1},
                            }
                        ],
                    }
                ]
            },
        )
    )
    item = board["items"][0]
    dispatch = assert_ok(
        await api_client.post(
            "/backlog-board/dispatch",
            json={"tribe": "Регрессия", "target_year": 2028, "target_quarter": "Q4"},
        )
    )
    assert dispatch["items"][0]["sent_to"] == ["2028-Q4"]
    initiative = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))["initiatives"][0]
    assert initiative["owner_team"] == "Команда Альфа"
    assert initiative["executors"][0]["team"] == "Проект Бета"
    assert initiative["total_estimate"] == 1

    pre_pi_payload = {
        "initiatives": [
            {
                "id": initiative["id"],
                "issue_key": "E2E-422-001",
                "title": "Проверка 422",
                "owner_team": "Команда Альфа",
                "owner_tribe": "Регрессия",
                "initiative_type": "Развитие функционала",
                "status": "planned",
                "goal_text": "Цель",
                "metric": "Метрика",
                "current_value": "0",
                "target_value": "1",
                "pre_planned": True,
                "executors": [
                    {
                        "team": "Проект Бета",
                        "tribe": "Регрессия",
                        "effort_by_competency": {"DEV": 1},
                    }
                ],
            }
        ]
    }
    assert_ok(await api_client.put(f"/pi-cycles/{cycle_id}/pre-pi", json=pre_pi_payload))

    unknown_team = deepcopy(pre_pi_payload)
    unknown_team["initiatives"][0]["executors"][0]["team"] = "Чужая команда"
    response = await api_client.put(f"/pi-cycles/{cycle_id}/pre-pi", json=unknown_team)
    assert response.status_code == 422
    assert assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))["initiatives"][0]["executors"][0]["team"] == "Проект Бета"

    locked_backlog_effort = deepcopy(pre_pi_payload)
    locked_backlog_effort["initiatives"][0]["executors"][0].update(
        {"team": "Проект Бета", "effort_by_competency": {"DEV": 2}}
    )
    locked_response = await api_client.put(
        f"/pi-cycles/{cycle_id}/pre-pi", json=locked_backlog_effort
    )
    assert locked_response.status_code == 422
    board_owned = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))[
        "initiatives"
    ][0]
    assert board_owned["owner_team"] == "Команда Альфа"
    assert board_owned["executors"][0]["team"] == "Проект Бета"
    assert board_owned["total_estimate"] == 1

    bad_competency = deepcopy(pre_pi_payload)
    bad_competency["initiatives"][0]["executors"][0]["effort_by_competency"] = {"UX": 2}
    assert (await api_client.put(f"/pi-cycles/{cycle_id}/pre-pi", json=bad_competency)).status_code == 422

    bad_sprint = deepcopy(pre_pi_payload)
    bad_sprint["initiatives"][0]["sprint_index"] = 3
    assert (await api_client.put(f"/pi-cycles/{cycle_id}/pre-pi", json=bad_sprint)).status_code == 422

    valid_risks = {
        "risks": [
            {
                "client_uid": "risk-atomic",
                "scope": "general",
                "description": "Сохранённый риск",
            }
        ]
    }
    assert_ok(await api_client.put(f"/pi-cycles/{cycle_id}/risks-board", json=valid_risks))
    invalid_risks = deepcopy(valid_risks)
    invalid_risks["risks"].append(
        {
            "client_uid": "risk-invalid",
            "scope": "team",
            "team": {"tribe": "Регрессия", "name": "Чужая команда"},
            "description": "Не должен сохраниться",
        }
    )
    assert (await api_client.put(f"/pi-cycles/{cycle_id}/risks-board", json=invalid_risks)).status_code == 422
    stored_risks = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/risks-board"))
    assert [row["client_uid"] for row in stored_risks["risks"]] == ["risk-atomic"]

    duplicate_backlog = {
        "items": [
            {"tribe": "Регрессия", "issue_key": "DUP-1"},
            {"tribe": "Регрессия", "issue_key": "dup-1"},
        ]
    }
    assert (await api_client.put("/backlog-board", json=duplicate_backlog)).status_code == 422
    assert [row["issue_key"] for row in assert_ok(await api_client.get("/backlog-board"))["items"]] == ["E2E-422-001"]


@pytest.mark.asyncio
async def test_legacy_posts_reject_cross_cycle_references(api_client):
    cycle, _ = await create_cycle_with_setup(api_client)
    other_cycle = assert_ok(
        await api_client.post(
            "/pi-cycles",
            json={"year": 2028, "quarter": "Q3", "sprint_count": 2},
        ),
        201,
    )
    teams = assert_ok(await api_client.get("/teams"))
    alpha = next(row for row in teams if row["name"] == "Команда Альфа")

    created = assert_ok(
        await api_client.post(
            f"/pi-cycles/{cycle['id']}/initiatives",
            json={
                "issue_key": "LEGACY-1",
                "title": "Legacy initiative",
                "owner_team_id": alpha["id"],
                "executors": [
                    {"team_id": alpha["id"], "effort_by_competency": {"SA": 1}}
                ],
            },
        ),
        201,
    )
    duplicate = await api_client.post(
        f"/pi-cycles/{cycle['id']}/initiatives",
        json={"issue_key": "legacy-1", "title": "Duplicate"},
    )
    assert duplicate.status_code == 422

    cross_cycle_goal = await api_client.post(
        f"/pi-cycles/{other_cycle['id']}/goals",
        json={
            "team_id": alpha["id"],
            "initiative_id": created["id"],
            "title": "Invalid goal",
        },
    )
    assert cross_cycle_goal.status_code == 422

    cross_cycle_risk = await api_client.post(
        f"/pi-cycles/{other_cycle['id']}/risks",
        json={
            "scope": "team",
            "team_id": alpha["id"],
            "description": "Invalid risk",
        },
    )
    assert cross_cycle_risk.status_code == 422
    assert len(assert_ok(await api_client.get(f"/pi-cycles/{cycle['id']}/initiatives"))) == 1
    assert assert_ok(await api_client.get(f"/pi-cycles/{other_cycle['id']}/goals")) == []
    assert assert_ok(await api_client.get(f"/pi-cycles/{other_cycle['id']}/risks")) == []


@pytest.mark.asyncio
async def test_optimistic_locking_rejects_stale_cycle_and_backlog_updates(api_client):
    cycle, setup = await create_cycle_with_setup(api_client, year=2029, quarter="Q1")
    cycle_id = cycle["id"]
    editor_version = setup["version"]
    setup_payload = {
        "start_date": setup["start_date"],
        "sprint_count": setup["sprint_count"],
        "pirs": setup["pirs"],
        "teams": setup["teams"],
        "goals": ["First editor value"],
        "tags": setup["tags"],
        "expected_version": editor_version,
    }

    first = assert_ok(
        await api_client.raw.put(f"/pi-cycles/{cycle_id}/setup", json=setup_payload)
    )
    assert first["version"] == editor_version + 1

    stale_payload = {**setup_payload, "goals": ["Stale editor value"]}
    stale = await api_client.raw.put(f"/pi-cycles/{cycle_id}/setup", json=stale_payload)
    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "version_conflict",
        "message": "Данные были изменены в другом окне",
        "aggregate": "pi_cycle",
        "expected_version": editor_version,
        "current_version": editor_version + 1,
    }
    persisted = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/setup"))
    assert persisted["goals"] == ["First editor value"]

    retry = assert_ok(
        await api_client.raw.put(
            f"/pi-cycles/{cycle_id}/setup",
            json={**stale_payload, "expected_version": persisted["version"]},
        )
    )
    assert retry["goals"] == ["Stale editor value"]
    assert retry["version"] == editor_version + 2

    missing_version = await api_client.raw.put(
        f"/pi-cycles/{cycle_id}/risks-board", json={"risks": []}
    )
    assert missing_version.status_code == 422

    backlog = assert_ok(await api_client.get("/backlog-board"))
    backlog_payload = {
        "expected_version": backlog["version"],
        "items": [
            {
                "tribe": "Регрессия",
                "issue_key": "LOCK-1",
                "title": "First backlog value",
            }
        ],
    }
    saved_backlog = assert_ok(
        await api_client.raw.put("/backlog-board", json=backlog_payload)
    )
    assert saved_backlog["version"] == backlog["version"] + 1

    stale_backlog = await api_client.raw.put(
        "/backlog-board",
        json={
            **backlog_payload,
            "items": [{**backlog_payload["items"][0], "title": "Stale backlog value"}],
        },
    )
    assert stale_backlog.status_code == 409
    assert stale_backlog.json()["detail"]["aggregate"] == "backlog_board"
    assert assert_ok(await api_client.get("/backlog-board"))["items"][0]["title"] == (
        "First backlog value"
    )


@pytest.mark.asyncio
async def test_pi_cycle_data_commands_return_canonical_server_view(api_client):
    data = assert_ok(
        await api_client.post(
            "/pi-cycle-data",
            json={
                "year": 2031,
                "quarter": "Q2",
                "start_date": "2031-04-07",
                "sprint_count": 2,
            },
        ),
        201,
    )
    path = f"/pi-cycles/{data['cycle']['id']}"
    assert data["cycle"]["setup_initialized"] is True
    assert data["schedule"]["end_date"] == "2031-05-04"
    assert data["schedule"]["total_workdays"] == 20
    assert len(data["schedule"]["sprints"][0]["weeks"]) == 2
    assert data["pirs"] == []

    data = assert_ok(
        await api_client.raw.post(
            f"{path}/pirs",
            json={
                "expected_version": data["cycle"]["version"],
                "name": "PIR 1",
                "date": "2031-04-21",
            },
        )
    )
    pir_id = data["pirs"][0]["id"]
    assert data["schedule"]["sprints"][1]["pirs"][0]["id"] == pir_id

    data = assert_ok(
        await api_client.raw.post(
            f"{path}/cycle-teams",
            json={
                "expected_version": data["cycle"]["version"],
                "tribe": "Data tribe",
                "name": "Data team",
                "team_type": "Agile",
                "excluded_from_goals": False,
                "competencies": ["sa", "DEV", "SA"],
            },
        )
    )
    assert data["teams"][0]["competencies"] == ["SA", "DEV"]


def backlog_write_row(row: dict, **changes) -> dict:
    payload = {
        "id": row["id"],
        "tribe": row["tribe"],
        "issue_key": row["issue_key"],
        "title": row["title"],
        "description": row["description"],
        "product": row["product"],
        "owner_team": row["owner_team"],
        "initiative_type": row["initiative_type"],
        "target_year": row["target_year"],
        "target_quarter": row["target_quarter"],
        "customer_priority": row["customer_priority"],
        "team_priority": row["team_priority"],
        "status": row["status"],
        "tshirt_size": row["tshirt_size"],
        "tags": row["tags"],
        "systems": row["systems"],
        "sort_order": row["sort_order"],
        "executors": [
            {
                "id": executor["id"],
                "team": executor["team"],
                "effort_by_competency": executor["effort_by_competency"],
            }
            for executor in row["executors"]
        ],
    }
    payload.update(changes)
    return payload


def backlog_command_row(row: dict, **changes) -> dict:
    payload = backlog_write_row(row)
    payload.pop("id")
    payload.pop("sort_order")
    payload.update(changes)
    return payload


@pytest.mark.asyncio
async def test_backlog_references_and_commands_are_scoped_to_selected_pi_cycle(api_client):
    first_cycle, first_setup = await create_cycle_with_setup(
        api_client, year=2032, quarter="Q1"
    )
    second_cycle = assert_ok(
        await api_client.post(
            "/pi-cycles",
            json={"year": 2032, "quarter": "Q2", "sprint_count": 2},
        ),
        201,
    )
    await api_client.put(
        f"/pi-cycles/{second_cycle['id']}/setup",
        json={
            "start_date": "2032-04-05",
            "sprint_count": 2,
            "teams": [
                {
                    "tribe": "Risk Tribe",
                    "name": "Outside Team",
                    "team_type": "Agile",
                    "competencies": ["BE"],
                }
            ],
        },
    )

    first = assert_ok(
        await api_client.get(
            "/backlog-board", params={"cycle_id": first_cycle["id"]}
        )
    )
    assert first["cycle_id"] == first_cycle["id"]
    assert [row["name"] for row in first["reference_data"]["tribes"]] == [
        "Регрессия"
    ]
    assert [row["name"] for row in first["reference_data"]["teams"]] == [
        "Команда Альфа",
        "Проект Бета",
    ]
    assert first["reference_data"]["teams"][0]["competencies"] == [
        "SA",
        "DEV",
        "QA",
    ]

    second = assert_ok(
        await api_client.get(
            "/backlog-board", params={"cycle_id": second_cycle["id"]}
        )
    )
    assert [row["name"] for row in second["reference_data"]["tribes"]] == [
        "Risk Tribe"
    ]
    assert [row["name"] for row in second["reference_data"]["teams"]] == [
        "Outside Team"
    ]
    assert second["reference_data"]["teams"][0]["competencies"] == ["BE"]

    rejected = await api_client.post(
        f"/backlog-board/items?cycle_id={first_cycle['id']}",
        json={
            "tribe": "Risk Tribe",
            "issue_key": "OUTSIDE-1",
            "owner_team": "Outside Team",
        },
    )
    assert rejected.status_code == 422

    reduced_setup = {
        "start_date": first_setup["start_date"],
        "sprint_count": first_setup["sprint_count"],
        "pirs": first_setup["pirs"],
        "teams": [first_setup["teams"][0]],
        "goals": first_setup["goals"],
        "tags": first_setup["tags"],
    }
    await api_client.put(f"/pi-cycles/{first_cycle['id']}/setup", json=reduced_setup)
    refreshed = assert_ok(
        await api_client.get(
            "/backlog-board", params={"cycle_id": first_cycle["id"]}
        )
    )
    assert [row["name"] for row in refreshed["reference_data"]["teams"]] == [
        "Команда Альфа"
    ]


@pytest.mark.asyncio
async def test_backlog_item_commands_keep_ids_validate_and_return_canonical_view(api_client):
    await create_cycle_with_setup(api_client, year=2032, quarter="Q2")
    initial = assert_ok(await api_client.get("/backlog-board"))
    assert initial["reference_data"]["tribes"][0]["name"] == "Регрессия"
    alpha_ref = next(
        row for row in initial["reference_data"]["teams"] if row["name"] == "Команда Альфа"
    )
    assert alpha_ref["competencies"] == ["SA", "DEV", "QA"]

    created = assert_ok(
        await api_client.post(
            "/backlog-board/items",
            json={
                "tribe": "Регрессия",
                "issue_key": "  CMD-1  ",
                "title": "Первая версия",
                "owner_team": "Команда Альфа",
                "target_year": 2032,
                "target_quarter": "Q2",
                "tags": ["tag", "tag", ""],
                "systems": ["CRM", "CRM"],
                "executors": [
                    {
                        "team": "Команда Альфа",
                        "effort_by_competency": {"sa": 1.25, "DEV": 2},
                    }
                ],
            },
        ),
        201,
    )
    first = created["items"][0]
    item_id = first["id"]
    executor_id = first["executors"][0]["id"]
    assert created["version"] == initial["version"] + 1
    assert first["issue_key"] == "CMD-1"
    assert first["tags"] == ["tag"]
    assert first["systems"] == ["CRM"]
    assert first["total_effort"] == 3.25

    command = backlog_write_row(first, issue_key="CMD-RENAMED", title="Вторая версия")
    command.pop("id")
    command.pop("sort_order")
    updated = assert_ok(
        await api_client.patch(f"/backlog-board/items/{item_id}", json=command)
    )
    edited = updated["items"][0]
    assert edited["id"] == item_id
    assert edited["executors"][0]["id"] == executor_id
    assert edited["issue_key"] == "CMD-RENAMED"
    assert updated["version"] == created["version"] + 1

    bad_competency = deepcopy(command)
    bad_competency["executors"][0]["effort_by_competency"] = {"UX": 10}
    rejected = await api_client.patch(
        f"/backlog-board/items/{item_id}", json=bad_competency
    )
    assert rejected.status_code == 422
    persisted = assert_ok(await api_client.get("/backlog-board"))
    assert persisted["version"] == updated["version"]
    assert persisted["items"][0]["title"] == "Вторая версия"

    manual_sent = deepcopy(command)
    manual_sent["status"] = "Отправлена в Pre PI Planning"
    assert (
        await api_client.patch(f"/backlog-board/items/{item_id}", json=manual_sent)
    ).status_code == 422


@pytest.mark.asyncio
async def test_backlog_bulk_swap_reorder_dispatch_and_confirmed_unlink_are_atomic(api_client):
    cycle, _ = await create_cycle_with_setup(api_client, year=2033, quarter="Q3")
    cycle_id = cycle["id"]
    board = assert_ok(
        await api_client.put(
            "/backlog-board",
            json={
                "items": [
                    {
                        "tribe": "Регрессия",
                        "issue_key": "SWAP-A",
                        "title": "A",
                        "owner_team": "Команда Альфа",
                        "target_year": 2033,
                        "target_quarter": "Q3",
                        "executors": [
                            {
                                "team": "Команда Альфа",
                                "effort_by_competency": {"SA": 1},
                            }
                        ],
                    },
                    {
                        "tribe": "Регрессия",
                        "issue_key": "SWAP-B",
                        "title": "B",
                        "owner_team": "Проект Бета",
                        "target_year": 2033,
                        "target_quarter": "Q3",
                        "executors": [
                            {
                                "team": "Проект Бета",
                                "effort_by_competency": {"DEV": 2},
                            }
                        ],
                    },
                ]
            },
        )
    )
    a, b = board["items"]
    swapped = assert_ok(
        await api_client.put(
            "/backlog-board",
            json={
                "items": [
                    backlog_write_row(a, issue_key="SWAP-B", sort_order=1),
                    backlog_write_row(b, issue_key="SWAP-A", sort_order=0),
                ]
            },
        )
    )
    by_id = {row["id"]: row for row in swapped["items"]}
    assert by_id[a["id"]]["issue_key"] == "SWAP-B"
    assert by_id[b["id"]]["issue_key"] == "SWAP-A"
    assert [row["id"] for row in swapped["items"]] == [b["id"], a["id"]]

    ordered = assert_ok(
        await api_client.put(
            "/backlog-board/order", json={"item_ids": [a["id"], b["id"]]}
        )
    )
    assert [row["id"] for row in ordered["items"]] == [a["id"], b["id"]]

    cycle_before = next(
        row for row in assert_ok(await api_client.get("/pi-cycles")) if row["id"] == cycle_id
    )
    dispatched = assert_ok(
        await api_client.post(
            "/backlog-board/dispatch",
            json={"tribe": "Регрессия", "target_year": 2033, "target_quarter": "Q3"},
        )
    )
    assert all(row["sent_to"] == ["2033-Q3"] for row in dispatched["items"])
    cycle_after = next(
        row for row in assert_ok(await api_client.get("/pi-cycles")) if row["id"] == cycle_id
    )
    assert cycle_after["version"] == cycle_before["version"] + 1
    assert len(assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))["initiatives"]) == 2

    repeat_version = dispatched["version"]
    repeated = assert_ok(
        await api_client.post(
            "/backlog-board/dispatch",
            json={"tribe": "Регрессия", "target_year": 2033, "target_quarter": "Q3"},
        )
    )
    assert repeated["version"] == repeat_version + 1
    assert assert_ok(await api_client.get("/backlog-board"))["version"] == repeated["version"]
    assert len(assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))["initiatives"]) == 2
    cycle_after_repeat = next(
        row for row in assert_ok(await api_client.get("/pi-cycles")) if row["id"] == cycle_id
    )
    assert cycle_after_repeat["version"] == cycle_after["version"] + 1

    cascade = await api_client.delete(f"/backlog-board/items/{a['id']}")
    assert cascade.status_code == 409
    assert cascade.json()["detail"]["code"] == "cascade_confirmation_required"
    assert len(assert_ok(await api_client.get("/backlog-board"))["items"]) == 2

    deleted = assert_ok(
        await api_client.delete(
            f"/backlog-board/items/{a['id']}", json={"confirm_cascade": True}
        )
    )
    assert [row["id"] for row in deleted["items"]] == [b["id"]]
    assert len(assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))["initiatives"]) == 2
    cycle_unlinked = next(
        row for row in assert_ok(await api_client.get("/pi-cycles")) if row["id"] == cycle_id
    )
    assert cycle_unlinked["version"] == cycle_after_repeat["version"] + 1


@pytest.mark.asyncio
async def test_backlog_dispatch_resyncs_already_sent_and_sends_new_items(api_client):
    cycle, _ = await create_cycle_with_setup(api_client, year=2034, quarter="Q1")
    cycle_id = cycle["id"]
    board = assert_ok(
        await api_client.put(
            "/backlog-board",
            json={
                "items": [
                    {
                        "tribe": "Регрессия",
                        "issue_key": "MIXED-OLD",
                        "title": "Already sent",
                        "owner_team": "Команда Альфа",
                        "target_year": 2034,
                        "target_quarter": "Q1",
                        "executors": [
                            {
                                "team": "Команда Альфа",
                                "effort_by_competency": {"SA": 1},
                            }
                        ],
                    }
                ]
            },
        )
    )
    dispatched = assert_ok(
        await api_client.post(
            "/backlog-board/dispatch",
            json={"tribe": "Регрессия", "target_year": 2034, "target_quarter": "Q1"},
        )
    )
    assert dispatched["items"][0]["issue_key"] == "MIXED-OLD"
    assert dispatched["items"][0]["sent_to"] == ["2034-Q1"]

    created = assert_ok(
        await api_client.post(
            "/backlog-board/items",
            json={
                "tribe": "Регрессия",
                "issue_key": "MIXED-NEW",
                "title": "Send later",
                "owner_team": "Команда Альфа",
                "target_year": 2034,
                "target_quarter": "Q1",
                # Собственные ресурсы необязательны: Pre PI создаст пустую
                # техническую строку владельца для будущих запросов на привлечение.
                "executors": [],
            },
        ),
        201,
    )
    assert len(created["items"]) == 2

    second_dispatch = assert_ok(
        await api_client.post(
            "/backlog-board/dispatch",
            json={"tribe": "Регрессия", "target_year": 2034, "target_quarter": "Q1"},
        )
    )
    by_key = {row["issue_key"]: row for row in second_dispatch["items"]}
    assert by_key["MIXED-OLD"]["sent_to"] == ["2034-Q1"]
    assert by_key["MIXED-NEW"]["sent_to"] == ["2034-Q1"]

    initiatives = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))[
        "initiatives"
    ]
    assert sorted(row["issue_key"] for row in initiatives) == ["MIXED-NEW", "MIXED-OLD"]
    assert {row["issue_key"] for row in initiatives} == {"MIXED-OLD", "MIXED-NEW"}
    external_only = next(row for row in initiatives if row["issue_key"] == "MIXED-NEW")
    assert external_only["total_estimate"] == 0
    assert external_only["executors"][0]["team"] == "Команда Альфа"
    assert external_only["executors"][0]["effort_by_competency"] == {}

    repeat_version = second_dispatch["version"]
    repeated = assert_ok(
        await api_client.post(
            "/backlog-board/dispatch",
            json={"tribe": "Регрессия", "target_year": 2034, "target_quarter": "Q1"},
        )
    )
    assert repeated["version"] == repeat_version + 1
    assert len(assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))["initiatives"]) == 2


@pytest.mark.asyncio
async def test_backlog_redispatch_updates_owned_fields_and_preserves_pre_pi_fields(api_client):
    cycle, _ = await create_cycle_with_setup(api_client, year=2035, quarter="Q2")
    cycle_id = cycle["id"]
    board = assert_ok(
        await api_client.put(
            "/backlog-board",
            json={
                "items": [
                    {
                        "tribe": "Регрессия",
                        "issue_key": "SYNC-LOCK-1",
                        "title": "Название из Бэклога",
                        "description": "Описание из Бэклога",
                        "product": "Продукт 1",
                        "owner_team": "Команда Альфа",
                        "initiative_type": "Развитие функционала",
                        "target_year": 2035,
                        "target_quarter": "Q2",
                        "customer_priority": "1",
                        "team_priority": "2",
                        "tshirt_size": "M",
                        "tags": ["E2E"],
                        "systems": ["CRM"],
                        "executors": [
                            {
                                "team": "Команда Альфа",
                                "effort_by_competency": {"SA": 2},
                            }
                        ],
                    }
                ]
            },
        )
    )
    backlog_item = board["items"][0]
    assert_ok(
        await api_client.post(
            "/backlog-board/dispatch",
            json={"tribe": "Регрессия", "target_year": 2035, "target_quarter": "Q2"},
        )
    )
    pre_pi = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))
    source = next(row for row in pre_pi["initiatives"] if row["issue_key"] == "SYNC-LOCK-1")
    source_id = source["id"]
    executor_id = source["executors"][0]["id"]
    assert {
        "issue_key",
        "title",
        "product",
        "owner_team_id",
        "initiative_type",
        "tshirt_size",
        "customer_priority",
        "team_priority",
        "tags",
        "executor_team",
        "effort_by_competency",
    } <= set(source["locked_fields"])

    moved = assert_ok(
        await api_client.post(
            f"/pi-cycles/{cycle_id}/pre-pi/initiatives/{source_id}/move",
            json={"target_block": "planned"},
        )
    )
    source = next(row for row in moved["initiatives"] if row["id"] == source_id)
    alpha = next(row for row in moved["teams"] if row["name"] == "Команда Альфа")
    beta = next(row for row in moved["teams"] if row["name"] == "Проект Бета")
    edited = assert_ok(
        await api_client.patch(
            f"/pi-cycles/{cycle_id}/pre-pi/initiatives/{source_id}",
            json={
                "goal_text": "Цель только Pre PI",
                "metric": "Метрика только Pre PI",
                "current_value": "10%",
                "target_value": "25%",
                "hypothesis": "Гипотеза только Pre PI",
                "redesign": "Редизайн только Pre PI",
                "executors": [
                    {
                        "id": executor_id,
                        "team_id": alpha["id"],
                        "team": alpha["name"],
                        "tribe": alpha["tribe"],
                        "effort_by_competency": {"SA": 2},
                        "attractions": [
                            {
                                "issue_key": "SYNC-EXT-1",
                                "target_team_id": beta["id"],
                                "sprint_index": 1,
                            }
                        ],
                    }
                ],
            },
        )
    )
    source = next(row for row in edited["initiatives"] if row["id"] == source_id)
    attraction_id = source["executors"][0]["attractions"][0]["id"]
    pre_pi_sort_order = source["sort_order"]

    locked_scalar = await api_client.patch(
        f"/pi-cycles/{cycle_id}/pre-pi/initiatives/{source_id}",
        json={"product": "Нельзя изменить в Pre PI"},
    )
    assert locked_scalar.status_code == 422
    assert "только на вкладке «Бэклог»" in locked_scalar.json()["detail"]
    locked_effort = await api_client.patch(
        f"/pi-cycles/{cycle_id}/pre-pi/initiatives/{source_id}",
        json={
            "executors": [
                {
                    "id": executor_id,
                    "team_id": alpha["id"],
                    "team": alpha["name"],
                    "tribe": alpha["tribe"],
                    "effort_by_competency": {"SA": 99},
                    "attractions": [],
                }
            ]
        },
    )
    assert locked_effort.status_code == 422

    current_backlog = assert_ok(await api_client.get("/backlog-board"))["items"][0]
    updated_board = assert_ok(
        await api_client.patch(
            f"/backlog-board/items/{backlog_item['id']}",
            json=backlog_command_row(
                current_backlog,
                issue_key="SYNC-LOCK-RENAMED",
                title="Обновлённое название",
                description="Обновлённое описание",
                product="Продукт 2",
                customer_priority="3",
                team_priority="4",
                tshirt_size="XL",
                executors=[
                    {
                        "id": current_backlog["executors"][0]["id"],
                        "team": "Команда Альфа",
                        "effort_by_competency": {"SA": 5, "DEV": 1},
                    }
                ],
            ),
        )
    )
    assert updated_board["items"][0]["tshirt_size"] == "XL"
    assert_ok(
        await api_client.post(
            "/backlog-board/dispatch",
            json={"tribe": "Регрессия", "target_year": 2035, "target_quarter": "Q2"},
        )
    )

    synced = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))
    source = next(
        row for row in synced["initiatives"] if row["issue_key"] == "SYNC-LOCK-RENAMED"
    )
    assert source["id"] == source_id
    assert source["title"] == "Обновлённое название"
    assert source["description"] == "Обновлённое описание"
    assert source["product"] == "Продукт 2"
    assert source["customer_priority"] == "3"
    assert source["team_priority"] == "4"
    assert source["tshirt_size"] == "XL"
    assert source["goal_text"] == "Цель только Pre PI"
    assert source["metric"] == "Метрика только Pre PI"
    assert source["current_value"] == "10%"
    assert source["target_value"] == "25%"
    assert source["hypothesis"] == "Гипотеза только Pre PI"
    assert source["redesign"] == "Редизайн только Pre PI"
    assert source["pre_planned"] is True
    assert source["sort_order"] == pre_pi_sort_order
    assert source["executors"][0]["id"] == executor_id
    assert source["executors"][0]["effort_by_competency"] == {"SA": 5.0, "DEV": 1.0}
    assert source["executors"][0]["attractions"][0]["id"] == attraction_id
    assert source["executors"][0]["attractions"][0]["issue_key"] == "SYNC-EXT-1"
    assert all(row["issue_key"] != "SYNC-LOCK-1" for row in synced["initiatives"])

    count_before_repeat = len(synced["initiatives"])
    assert_ok(
        await api_client.post(
            "/backlog-board/dispatch",
            json={"tribe": "Регрессия", "target_year": 2035, "target_quarter": "Q2"},
        )
    )
    repeated = assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))
    assert len(repeated["initiatives"]) == count_before_repeat
    assert next(
        row for row in repeated["initiatives"] if row["issue_key"] == "SYNC-LOCK-RENAMED"
    )["id"] == source_id


@pytest.mark.asyncio
async def test_pi_cycle_data_bulk_commands_keep_ids_and_rollback(api_client):
    data = assert_ok(
        await api_client.post(
            "/pi-cycle-data",
            json={
                "year": 2031,
                "quarter": "Q2",
                "start_date": "2031-04-07",
                "sprint_count": 2,
            },
        ),
        201,
    )
    path = f"/pi-cycles/{data['cycle']['id']}"
    data = assert_ok(
        await api_client.raw.post(
            f"{path}/pirs",
            json={
                "expected_version": data["cycle"]["version"],
                "name": "PIR 1",
                "date": "2031-04-21",
            },
        )
    )
    pir_id = data["pirs"][0]["id"]
    data = assert_ok(
        await api_client.raw.post(
            f"{path}/cycle-teams",
            json={
                "expected_version": data["cycle"]["version"],
                "tribe": "Data tribe",
                "name": "Data team",
                "team_type": "Agile",
                "excluded_from_goals": False,
                "competencies": ["SA", "DEV"],
            },
        )
    )

    data = assert_ok(
        await api_client.raw.post(
            f"{path}/goal-options",
            json={"expected_version": data["cycle"]["version"], "name": "Growth"},
        )
    )
    data = assert_ok(
        await api_client.raw.post(
            f"{path}/tags",
            json={"expected_version": data["cycle"]["version"], "name": "Client"},
        )
    )
    version_before_bulk = data["cycle"]["version"]
    stable_ids = {
        "pir": data["pirs"][0]["id"],
        "team": data["teams"][0]["id"],
        "goal": data["goal_options"][0]["id"],
        "tag": data["tags"][0]["id"],
    }
    data = assert_ok(
        await api_client.raw.put(
            f"{path}/data",
            json={
                "expected_version": version_before_bulk,
                "start_date": "2031-04-07",
                "sprint_count": 3,
                "pirs": [
                    {
                        "id": stable_ids["pir"],
                        "name": "PIR bulk",
                        "date": "2031-04-22",
                    }
                ],
                "teams": [
                    {
                        "id": stable_ids["team"],
                        "tribe": "Data tribe",
                        "name": "Data team renamed",
                        "team_type": "Agile",
                        "excluded_from_goals": True,
                        "competencies": ["SA", "DEV"],
                    }
                ],
                "goal_options": [{"id": stable_ids["goal"], "name": "Growth bulk"}],
                "tags": [{"id": stable_ids["tag"], "name": "Client bulk"}],
            },
        )
    )
    assert data["cycle"]["version"] == version_before_bulk + 1
    assert data["pirs"][0]["id"] == stable_ids["pir"]
    assert data["teams"][0]["id"] == stable_ids["team"]
    assert data["goal_options"][0]["id"] == stable_ids["goal"]
    assert data["tags"][0]["id"] == stable_ids["tag"]
    assert data["teams"][0]["excluded_from_goals"] is True
    reloaded = assert_ok(await api_client.get(f"{path}/data"))
    assert reloaded == data

    rejected = await api_client.raw.patch(
        f"{path}/pirs/{pir_id}",
        json={
            "expected_version": data["cycle"]["version"],
            "name": "PIR outside",
            "date": "2031-06-01",
        },
    )
    assert rejected.status_code == 422
    after_rejected = assert_ok(await api_client.get(f"{path}/data"))
    assert after_rejected["cycle"]["version"] == data["cycle"]["version"]
    assert after_rejected["pirs"][0]["name"] == "PIR bulk"


@pytest.mark.asyncio
async def test_pi_cycle_data_allows_team_without_competencies(api_client):
    cycle = assert_ok(
        await api_client.post(
            "/pi-cycles",
            json={
                "year": 2036,
                "quarter": "Q1",
                "start_date": "2036-01-08",
                "sprint_count": 6,
            },
        ),
        201,
    )
    path = f"/pi-cycles/{cycle['id']}"

    data = assert_ok(
        await api_client.raw.put(
            f"{path}/data",
            json={
                "expected_version": cycle["version"],
                "start_date": "2036-01-08",
                "sprint_count": 6,
                "pirs": [],
                "regressions": [],
                "teams": [
                    {
                        "id": None,
                        "tribe": "LEGAL",
                        "name": "LEGAL",
                        "team_type": "Agile",
                        "excluded_from_goals": False,
                        "competencies": [],
                    }
                ],
                "goal_options": [],
                "tags": [],
            },
        )
    )

    legal_team = data["teams"][0]
    assert legal_team["tribe"] == "LEGAL"
    assert legal_team["name"] == "LEGAL"
    assert legal_team["competencies"] == []
    reloaded = assert_ok(await api_client.get(f"{path}/data"))
    assert reloaded["teams"][0]["competencies"] == []


@pytest.mark.asyncio
async def test_pi_cycle_team_delete_requires_confirmation_and_cascades(api_client):
    cycle = assert_ok(
        await api_client.post(
            "/pi-cycles",
            json={
                "year": 2031,
                "quarter": "Q3",
                "start_date": "2031-07-07",
                "sprint_count": 2,
            },
        ),
        201,
    )
    path = f"/pi-cycles/{cycle['id']}"
    data = assert_ok(await api_client.get(f"{path}/data"))
    data = assert_ok(
        await api_client.raw.post(
            f"{path}/cycle-teams",
            json={
                "expected_version": data["cycle"]["version"],
                "tribe": "Cascade tribe",
                "name": "Cascade team",
                "competencies": ["SA"],
            },
        )
    )
    cycle_team_id = data["teams"][0]["id"]
    capacity = assert_ok(
        await api_client.put(
            f"{path}/capacity",
            json={
                "teams": [
                    {
                        "tribe": "Cascade tribe",
                        "team": "Cascade team",
                        "members": [
                            {
                                "client_uid": "cascade-person",
                                "full_name": "Person",
                                "competency": "SA",
                            }
                        ],
                    }
                ]
            },
        )
    )
    risks = assert_ok(
        await api_client.put(
            f"{path}/risks-board",
            json={
                "risks": [
                    {
                        "client_uid": "cascade-risk",
                        "scope": "team",
                        "team": {"tribe": "Cascade tribe", "name": "Cascade team"},
                        "description": "Risk",
                    }
                ]
            },
        )
    )
    assert capacity["teams"][0]["members"]
    current_version = risks["version"]

    confirmation = await api_client.raw.request(
        "DELETE",
        f"{path}/cycle-teams/{cycle_team_id}",
        json={"expected_version": current_version, "confirm_cascade": False},
    )
    assert confirmation.status_code == 409
    assert confirmation.json()["detail"]["code"] == "cascade_confirmation_required"

    deleted = assert_ok(
        await api_client.raw.request(
            "DELETE",
            f"{path}/cycle-teams/{cycle_team_id}",
            json={"expected_version": current_version, "confirm_cascade": True},
        )
    )
    assert deleted["teams"] == []
    assert assert_ok(await api_client.get(f"{path}/capacity"))["teams"] == []
    assert assert_ok(await api_client.get(f"{path}/risks-board"))["risks"] == []


@pytest.mark.asyncio
async def test_bulk_pi_data_atomically_swaps_two_tags_and_two_teams(api_client):
    cycle, _ = await create_cycle_with_setup(api_client, year=2032, quarter="Q1")
    path = f"/pi-cycles/{cycle['id']}"
    data = assert_ok(await api_client.get(f"{path}/data"))
    data = assert_ok(
        await api_client.raw.post(
            f"{path}/tags",
            json={"expected_version": data["cycle"]["version"], "name": "Second"},
        )
    )
    assert_ok(
        await api_client.put(
            f"{path}/pre-pi",
            json={
                "initiatives": [
                    {
                        "issue_key": "SWAP-1",
                        "title": "Swap references",
                        "owner_team": "Команда Альфа",
                        "owner_tribe": "Регрессия",
                        "status": "planned",
                        "pre_planned": True,
                        "sprint_index": 0,
                        "tags": ["E2E"],
                        "executors": [
                            {
                                "team": "Команда Альфа",
                                "tribe": "Регрессия",
                                "effort_by_competency": {"SA": 1},
                            }
                        ],
                    }
                ]
            },
        )
    )
    assert_ok(
        await api_client.put(
            f"{path}/capacity",
            json={
                "teams": [
                    {
                        "tribe": "Регрессия",
                        "team": "Команда Альфа",
                        "members": [
                            {
                                "client_uid": "swap-member",
                                "full_name": "Swap Member",
                                "competency": "SA",
                            }
                        ],
                    }
                ]
            },
        )
    )
    assert_ok(
        await api_client.put(
            f"{path}/risks-board",
            json={
                "risks": [
                    {
                        "client_uid": "swap-risk",
                        "scope": "team",
                        "team": {"tribe": "Регрессия", "name": "Команда Альфа"},
                        "description": "Swap risk",
                    }
                ]
            },
        )
    )
    data = assert_ok(await api_client.get(f"{path}/data"))
    version_before = data["cycle"]["version"]
    alpha = next(row for row in data["teams"] if row["name"] == "Команда Альфа")
    beta = next(row for row in data["teams"] if row["name"] == "Проект Бета")
    first_tag, second_tag = data["tags"]

    swapped = assert_ok(
        await api_client.raw.put(
            f"{path}/data",
            json={
                "expected_version": version_before,
                "start_date": data["cycle"]["start_date"],
                "sprint_count": data["cycle"]["sprint_count"],
                "pirs": data["pirs"],
                "teams": [
                    {
                        "id": alpha["id"],
                        "tribe": beta["tribe"],
                        "name": beta["name"],
                        "team_type": alpha["team_type"],
                        "excluded_from_goals": alpha["excluded_from_goals"],
                        "competencies": alpha["competencies"],
                    },
                    {
                        "id": beta["id"],
                        "tribe": alpha["tribe"],
                        "name": alpha["name"],
                        "team_type": beta["team_type"],
                        "excluded_from_goals": beta["excluded_from_goals"],
                        "competencies": beta["competencies"],
                    },
                ],
                "goal_options": data["goal_options"],
                "tags": [
                    {"id": first_tag["id"], "name": second_tag["name"]},
                    {"id": second_tag["id"], "name": first_tag["name"]},
                ],
            },
        )
    )
    assert swapped["cycle"]["version"] == version_before + 1
    assert next(row for row in swapped["teams"] if row["id"] == alpha["id"])["name"] == (
        "Проект Бета"
    )
    assert next(row for row in swapped["tags"] if row["id"] == first_tag["id"])["name"] == (
        "Second"
    )
    pre_pi = assert_ok(await api_client.get(f"{path}/pre-pi"))["initiatives"][0]
    assert pre_pi["owner_team"] == "Проект Бета"
    assert pre_pi["executors"][0]["team"] == "Проект Бета"
    assert pre_pi["tags"] == ["Second"]
    assert assert_ok(await api_client.get(f"{path}/capacity"))["teams"][0]["team"] == (
        "Проект Бета"
    )
    assert assert_ok(await api_client.get(f"{path}/risks-board"))["risks"][0]["team"][
        "name"
    ] == "Проект Бета"


@pytest.mark.asyncio
async def test_bulk_pi_data_combined_cascades_are_confirmed_and_atomic(api_client):
    cycle, _ = await create_cycle_with_setup(api_client, year=2032, quarter="Q2")
    path = f"/pi-cycles/{cycle['id']}"
    assert_ok(
        await api_client.put(
            f"{path}/pre-pi",
            json={
                "initiatives": [
                    {
                        "issue_key": "CASCADE-A",
                        "title": "Removed team initiative",
                        "owner_team": "Команда Альфа",
                        "owner_tribe": "Регрессия",
                        "status": "planned",
                        "pre_planned": True,
                        "sprint_index": 2,
                        "tags": ["E2E"],
                        "executors": [
                            {
                                "team": "Команда Альфа",
                                "tribe": "Регрессия",
                                "effort_by_competency": {"SA": 1},
                            }
                        ],
                    },
                    {
                        "issue_key": "CASCADE-B",
                        "title": "Out of range initiative",
                        "owner_team": "Проект Бета",
                        "owner_tribe": "Регрессия",
                        "status": "planned",
                        "pre_planned": True,
                        "sprint_index": 2,
                        "tags": ["E2E"],
                        "executors": [
                            {
                                "team": "Проект Бета",
                                "tribe": "Регрессия",
                                "effort_by_competency": {"SA": 1},
                            }
                        ],
                    },
                ]
            },
        )
    )
    assert_ok(
        await api_client.put(
            f"{path}/capacity",
            json={
                "teams": [
                    {
                        "tribe": "Регрессия",
                        "team": "Команда Альфа",
                        "members": [
                            {
                                "client_uid": "cascade-combined-member",
                                "full_name": "Cascade Member",
                                "competency": "SA",
                            }
                        ],
                    }
                ]
            },
        )
    )
    assert_ok(
        await api_client.put(
            f"{path}/risks-board",
            json={
                "risks": [
                    {
                        "client_uid": "cascade-combined-risk",
                        "scope": "team",
                        "team": {"tribe": "Регрессия", "name": "Команда Альфа"},
                        "description": "Combined cascade risk",
                    }
                ]
            },
        )
    )
    data = assert_ok(await api_client.get(f"{path}/data"))
    version_before = data["cycle"]["version"]
    beta = next(row for row in data["teams"] if row["name"] == "Проект Бета")
    payload = {
        "expected_version": version_before,
        "start_date": data["cycle"]["start_date"],
        "sprint_count": 1,
        "pirs": [],
        "teams": [beta],
        "goal_options": data["goal_options"],
        "tags": [],
        "confirm_cascade": False,
    }

    confirmation = await api_client.raw.put(f"{path}/data", json=payload)
    assert confirmation.status_code == 409
    assert confirmation.json()["detail"]["code"] == "cascade_confirmation_required"
    unchanged = assert_ok(await api_client.get(f"{path}/data"))
    assert unchanged["cycle"]["version"] == version_before
    assert unchanged["cycle"]["sprint_count"] == 3
    assert len(unchanged["teams"]) == 2
    assert unchanged["pirs"]
    assert unchanged["tags"]

    cascaded = assert_ok(
        await api_client.raw.put(
            f"{path}/data",
            json={**payload, "confirm_cascade": True},
        )
    )
    assert cascaded["cycle"]["version"] == version_before + 1
    assert cascaded["cycle"]["sprint_count"] == 1
    assert [row["name"] for row in cascaded["teams"]] == ["Проект Бета"]
    assert cascaded["pirs"] == []
    assert cascaded["tags"] == []
    initiatives = {
        row["issue_key"]: row
        for row in assert_ok(await api_client.get(f"{path}/pre-pi"))["initiatives"]
    }
    assert initiatives["CASCADE-A"]["owner_team"] == ""
    assert initiatives["CASCADE-A"]["executors"] == []
    assert initiatives["CASCADE-A"]["sprint_index"] is None
    assert initiatives["CASCADE-A"]["tags"] == []
    assert initiatives["CASCADE-B"]["sprint_index"] is None
    assert initiatives["CASCADE-B"]["tags"] == []
    capacity_teams = assert_ok(await api_client.get(f"{path}/capacity"))["teams"]
    assert [row["team"] for row in capacity_teams] == ["Проект Бета"]
    assert capacity_teams[0]["members"] == []
    assert assert_ok(await api_client.get(f"{path}/risks-board"))["risks"] == []


@pytest.mark.asyncio
async def test_pre_pi_focused_commands_return_canonical_read_model(api_client):
    cycle, _ = await create_cycle_with_setup(api_client, year=2033, quarter="Q1")
    path = f"/pi-cycles/{cycle['id']}"
    created = assert_ok(
        await api_client.put(
            f"{path}/pre-pi",
            json={
                "initiatives": [
                    {
                        "issue_key": "CMD-1",
                        "title": "Command source",
                        "owner_team": "Команда Альфа",
                        "owner_tribe": "Регрессия",
                        "initiative_type": "Развитие функционала",
                        "goal_text": "Цель регрессии",
                        "metric": "Metric",
                        "current_value": "0",
                        "target_value": "1",
                        "executors": [
                            {
                                "team": "Команда Альфа",
                                "tribe": "Регрессия",
                                "effort_by_competency": {"SA": 2, "DEV": 3},
                            }
                        ],
                    },
                    {
                        "issue_key": "CMD-2",
                        "title": "Attraction target",
                        "owner_team": "Проект Бета",
                        "owner_tribe": "Регрессия",
                        "executors": [
                            {
                                "team": "Проект Бета",
                                "tribe": "Регрессия",
                                "effort_by_competency": {"SA": 1},
                            }
                        ],
                    },
                ]
            },
        )
    )
    first = next(row for row in created["backlog"] if row["issue_key"] == "CMD-1")
    second = next(row for row in created["backlog"] if row["issue_key"] == "CMD-2")
    alpha = next(row for row in created["teams"] if row["name"] == "Команда Альфа")
    beta = next(row for row in created["teams"] if row["name"] == "Проект Бета")
    assert created["cycle"]["id"] == cycle["id"]
    assert created["goal_options"][0]["name"] == "Цель регрессии"
    assert first["total_estimate"] == 5
    assert str(alpha["id"]) in created["capacity"]["teams"]

    moved_first = assert_ok(
        await api_client.post(
            f"{path}/pre-pi/initiatives/{first['id']}/move",
            json={"target_block": "planned"},
        )
    )
    first = next(row for row in moved_first["planned"] if row["issue_key"] == "CMD-1")
    assert [row["issue_key"] for row in moved_first["planned"]] == ["CMD-1"]

    self_attraction = await api_client.patch(
        f"{path}/pre-pi/initiatives/{first['id']}",
        json={
            "executors": [
                {
                    "id": first["executors"][0]["id"],
                    "team_id": alpha["id"],
                    "team": alpha["name"],
                    "tribe": alpha["tribe"],
                    "effort_by_competency": {"SA": 3, "DEV": 2},
                    "attractions": [
                        {
                            "issue_key": "SELF-ATTRACTION",
                            "target_team_id": alpha["id"],
                            "sprint_index": 1,
                        }
                    ],
                }
            ]
        },
    )
    assert self_attraction.status_code == 422
    assert "владельца текущей доски" in self_attraction.json()["detail"]

    edited = assert_ok(
        await api_client.patch(
            f"{path}/pre-pi/initiatives/{first['id']}",
            json={
                "description": "Edited atomically",
                "executors": [
                    {
                        "id": first["executors"][0]["id"],
                        "team_id": alpha["id"],
                        "team": alpha["name"],
                        "tribe": alpha["tribe"],
                        "effort_by_competency": {"SA": 4, "DEV": 3},
                        "attractions": [
                            {
                                "target_initiative_id": None,
                                "issue_key": "EXTERNAL-404",
                                "target_team_id": beta["id"],
                                "sprint_index": 1,
                            }
                        ],
                    }
                ],
            },
        )
    )
    edited_first = next(row for row in edited["initiatives"] if row["id"] == first["id"])
    assert edited_first["id"] == first["id"]
    assert edited_first["executors"][0]["id"] == first["executors"][0]["id"]
    assert edited_first["owner_estimate"] == 7
    assert edited_first["attraction_estimate"] == 0
    assert edited_first["pending_attraction_estimate"] == 0
    assert edited_first["total_estimate"] == 7
    attraction = edited_first["executors"][0]["attractions"][0]
    assert attraction["id"]
    assert attraction["issue_key"] == "EXTERNAL-404"
    assert attraction["approval_status"] == "pending"
    assert attraction["visual_state"] == "purple"
    assert attraction["effort_by_competency"] == {}
    assert attraction["resource_estimate"] == 0
    assert attraction["included_in_total"] is True
    external_before_submit = next(
        row for row in edited["backlog"] if row["issue_key"] == "EXTERNAL-404"
    )
    assert attraction["target_initiative_id"] == external_before_submit["id"]
    assert external_before_submit["owner_team"] == "Команда Альфа"
    assert external_before_submit["pre_planned"] is False
    assert external_before_submit["status"] == "backlog"
    assert external_before_submit["on_board"] is False
    assert external_before_submit["sprint_index"] == 1
    assert external_before_submit["executors"][0]["team"] == "Проект Бета"

    # LEGAL/DEV scenario: the source team remains the factual task owner, while
    # the target board owner enters its own competencies into the same card.
    edited_external = assert_ok(
        await api_client.patch(
            f"{path}/pre-pi/initiatives/{external_before_submit['id']}",
            json={
                "executors": [
                    {
                        "id": external_before_submit["executors"][0]["id"],
                        "team_id": beta["id"],
                        "team": beta["name"],
                        "tribe": beta["tribe"],
                        "effort_by_competency": {"SA": 6},
                        "attractions": [],
                    }
                ]
            },
        )
    )
    external_after_effort = next(
        row for row in edited_external["initiatives"]
        if row["issue_key"] == "EXTERNAL-404"
    )
    assert external_after_effort["owner_team"] == "Команда Альфа"
    assert external_after_effort["executors"][0]["team"] == "Проект Бета"
    assert external_after_effort["executors"][0]["effort_by_competency"] == {"SA": 6.0}
    assert external_after_effort["total_estimate"] == 6
    source_after_external_effort = next(
        row for row in edited_external["initiatives"] if row["id"] == first["id"]
    )
    assert source_after_external_effort["owner_estimate"] == 7
    assert source_after_external_effort["attraction_estimate"] == 6
    assert source_after_external_effort["pending_attraction_estimate"] == 6
    assert source_after_external_effort["total_estimate"] == 13
    source_attraction = source_after_external_effort["executors"][0]["attractions"][0]
    assert source_attraction["effort_by_competency"] == {"SA": 6.0}
    assert source_attraction["resource_estimate"] == 6

    submitted = assert_ok(
        await api_client.post(
            f"{path}/pre-pi/submit",
            json={"teams": [{"tribe": "Регрессия", "name": "Команда Альфа"}]},
        )
    )
    assert submitted["board_added"] == 1
    assert submitted["attractions_added"] == 0
    external = next(
        row for row in submitted["pre_pi"]["initiatives"]
        if row["issue_key"] == "EXTERNAL-404"
    )
    assert external["owner_team"] == "Команда Альфа"
    assert external["pre_planned"] is False
    assert external["on_board"] is False
    assert external["sprint_index"] == 1
    assert external["executors"][0]["team"] == "Проект Бета"
    assert sum(
        row["issue_key"] == "EXTERNAL-404"
        for row in submitted["pre_pi"]["initiatives"]
    ) == 1

    planned_external = assert_ok(
        await api_client.post(
            f"{path}/pre-pi/initiatives/{external['id']}/move",
            json={"target_block": "planned"},
        )
    )
    assert next(
        row for row in planned_external["planned"]
        if row["issue_key"] == "EXTERNAL-404"
    )["owner_team"] == "Команда Альфа"
    beta_submitted = assert_ok(
        await api_client.post(
            f"{path}/pre-pi/submit",
            json={"teams": [{"tribe": "Регрессия", "name": "Проект Бета"}]},
        )
    )
    beta_external = next(
        row for row in beta_submitted["pre_pi"]["initiatives"]
        if row["issue_key"] == "EXTERNAL-404"
    )
    assert beta_submitted["board_added"] == 1
    assert beta_external["on_board"] is True
    assert beta_external["sprint_index"] == 1

    cancelled = assert_ok(
        await api_client.patch(
            f"{path}/pre-pi/initiatives/{first['id']}",
            json={
                "executors": [
                    {
                        "id": first["executors"][0]["id"],
                        "team_id": alpha["id"],
                        "team": alpha["name"],
                        "tribe": alpha["tribe"],
                        "effort_by_competency": {"SA": 4, "DEV": 3},
                        "attractions": [],
                    }
                ]
            },
        )
    )
    assert all(
        row["issue_key"] != "EXTERNAL-404"
        for row in cancelled["initiatives"]
    )
    cancelled_source = next(row for row in cancelled["initiatives"] if row["id"] == first["id"])
    assert cancelled_source["owner_estimate"] == 7
    assert cancelled_source["attraction_estimate"] == 0
    assert cancelled_source["total_estimate"] == 7
    team_boards_after_cancel = assert_ok(
        await api_client.get(f"{path}/team-boards")
    )
    assert all(
        row["issue_key"] != "EXTERNAL-404"
        for row in team_boards_after_cancel["initiatives"]
    )
    goals_after_cancel = assert_ok(await api_client.get(f"{path}/goals-board"))
    assert all(
        external["id"] not in goal["initiative_ids"]
        for goal in goals_after_cancel["goals"]
    )
    cascade = await api_client.post(
        f"{path}/pre-pi/initiatives/{first['id']}/move",
        json={"target_block": "backlog"},
    )
    assert cascade.status_code == 409
    assert cascade.json()["detail"]["code"] == "cascade_confirmation_required"
    returned = assert_ok(
        await api_client.post(
            f"{path}/pre-pi/initiatives/{first['id']}/move",
            json={"target_block": "backlog", "confirm_cascade": True},
        )
    )
    returned_first = next(row for row in returned["backlog"] if row["id"] == first["id"])
    assert returned_first["on_board"] is False
    assert returned_first["status"] == "backlog"


@pytest.mark.asyncio
async def test_pre_pi_attraction_without_sprint_goes_to_executor_board_backlog(api_client):
    cycle, _ = await create_cycle_with_setup(api_client, year=2034, quarter="Q4")
    path = f"/pi-cycles/{cycle['id']}"
    created = assert_ok(
        await api_client.put(
            f"{path}/pre-pi",
            json={
                "initiatives": [
                    {
                        "issue_key": "ATTR-SOURCE",
                        "title": "Source initiative",
                        "owner_team": "Команда Альфа",
                        "owner_tribe": "Регрессия",
                        "executors": [
                            {
                                "team": "Команда Альфа",
                                "tribe": "Регрессия",
                                "effort_by_competency": {"SA": 1},
                            }
                        ],
                    }
                ]
            },
        )
    )
    source = next(row for row in created["backlog"] if row["issue_key"] == "ATTR-SOURCE")
    alpha = next(row for row in created["teams"] if row["name"] == "Команда Альфа")
    beta = next(row for row in created["teams"] if row["name"] == "Проект Бета")

    edited = assert_ok(
        await api_client.patch(
            f"{path}/pre-pi/initiatives/{source['id']}",
            json={
                "executors": [
                    {
                        "id": source["executors"][0]["id"],
                        "team_id": alpha["id"],
                        "team": alpha["name"],
                        "tribe": alpha["tribe"],
                        "effort_by_competency": {"SA": 1},
                        "attractions": [
                            {
                                "issue_key": "ATTR-BACKLOG",
                                "target_team_id": beta["id"],
                                "sprint_index": None,
                            }
                        ],
                    }
                ],
            },
        )
    )

    attraction = next(
        row for row in edited["initiatives"] if row["issue_key"] == "ATTR-SOURCE"
    )["executors"][0]["attractions"][0]
    assert attraction["sprint_index"] is None

    target = next(row for row in edited["backlog"] if row["issue_key"] == "ATTR-BACKLOG")
    assert target["owner_team"] == "Команда Альфа"
    assert target["executors"][0]["team"] == "Проект Бета"
    assert target["pre_planned"] is False
    assert target["on_board"] is True
    assert target["status"] == "on_board"
    assert target["sprint_index"] is None

    board_target = next(
        row
        for row in assert_ok(await api_client.get(f"{path}/team-boards"))["initiatives"]
        if row["issue_key"] == "ATTR-BACKLOG"
    )
    assert board_target["on_board"] is True
    assert board_target["sprint_index"] is None


@pytest.mark.asyncio
async def test_goals_and_risks_focused_commands_are_atomic_and_versioned(api_client):
    cycle, _ = await create_cycle_with_setup(api_client, year=2034, quarter="Q2")
    cycle_id = cycle["id"]
    path = f"/pi-cycles/{cycle_id}"
    pre_pi = assert_ok(
        await api_client.put(
            f"{path}/pre-pi",
            json={
                "initiatives": [
                    {
                        "issue_key": "ATOM-1",
                        "title": "Atomic initiative",
                        "owner_team": "Команда Альфа",
                        "owner_tribe": "Регрессия",
                        "goal_text": "Atomic goal",
                        "executors": [
                            {
                                "team": "Команда Альфа",
                                "tribe": "Регрессия",
                                "effort_by_competency": {"SA": 1},
                            }
                        ],
                    }
                ]
            },
        )
    )
    initiative = pre_pi["initiatives"][0]
    alpha = next(row for row in pre_pi["teams"] if row["name"] == "Команда Альфа")
    current_version = pre_pi["version"]

    stale_goal = await api_client.raw.post(
        f"{path}/goals-board/goals",
        json={
            "expected_version": current_version - 1,
            "team_id": alpha["id"],
            "title": "Stale goal",
        },
    )
    assert stale_goal.status_code == 409
    assert stale_goal.json()["detail"]["code"] == "version_conflict"


@pytest.mark.asyncio
async def test_team_board_focused_commands_capacity_assignments_and_cascades(api_client):
    cycle, _ = await create_cycle_with_setup(api_client, year=2035, quarter="Q3")
    path = f"/pi-cycles/{cycle['id']}"
    pre_pi = assert_ok(
        await api_client.put(
            f"{path}/pre-pi",
            json={
                "initiatives": [
                    {
                        "issue_key": "TEAM-CMD-1",
                        "title": "Team command source",
                        "owner_team": "Команда Альфа",
                        "owner_tribe": "Регрессия",
                        "initiative_type": "Развитие функционала",
                        "tags": ["E2E"],
                        "goal_text": "Командная цель",
                        "metric": "Командная метрика",
                        "current_value": "0",
                        "target_value": "1",
                        "executors": [
                            {
                                "team": "Команда Альфа",
                                "tribe": "Регрессия",
                                "effort_by_competency": {"SA": 3},
                            }
                        ],
                    }
                ]
            },
        )
    )
    initiative = pre_pi["backlog"][0]
    pre_pi = assert_ok(
        await api_client.post(
            f"{path}/pre-pi/initiatives/{initiative['id']}/move",
            json={"target_block": "planned"},
        )
    )
    initiative = pre_pi["planned"][0]
    submitted = assert_ok(
        await api_client.post(
            f"{path}/pre-pi/submit",
            json={"teams": [{"tribe": "Регрессия", "name": "Команда Альфа"}]},
        )
    )
    version = submitted["version"]

    capacity = assert_ok(
        await api_client.raw.post(
            f"{path}/capacity/members",
            json={
                "expected_version": version,
                "tribe": "Регрессия",
                "team": "Команда Альфа",
                "client_uid": "team-member-1",
                "full_name": "Иванов Иван",
                "competency": "SA",
                "rate": 1,
                "vacation_ranges": [],
                "extra_unavailable_ranges": [],
                "ceremony_percent": 10,
                "risk_percent": 5,
            },
        ),
        201,
    )
    member = next(row for row in capacity["teams"] if row["team"] == "Команда Альфа")[
        "members"
    ][0]
    assert len(member["weeks"]["0"]) == 2
    assert [row["week_index"] for row in member["weeks"]["0"]] == [0, 1]

    board = assert_ok(
        await api_client.raw.post(
            f"{path}/team-boards/initiatives/{initiative['id']}/stories",
            json={
                "expected_version": capacity["version"],
                "client_uid": "team-story-1",
                "external_key": "TEAM-CMD-1-S1",
                "title": "Server story",
                "effort_by_competency": {"SA": 2},
                "sprint_index": 0,
                "week_index": 1,
            },
        ),
        201,
    )
    story = board["initiatives"][0]["stories"][0]
    invalid_assignee = await api_client.raw.post(
        f"{path}/team-boards/initiatives/{initiative['id']}/work-items",
        json={
            "expected_version": board["version"],
            "client_uid": "team-work-invalid",
            "assignee_name": "Неизвестный сотрудник",
            "competency": "SA",
            "effort": 1,
            "sprint_index": 0,
            "week_index": 1,
        },
    )
    assert invalid_assignee.status_code == 422

    board = assert_ok(
        await api_client.raw.post(
            f"{path}/team-boards/initiatives/{initiative['id']}/work-items",
            json={
                "expected_version": board["version"],
                "client_uid": "team-work-1",
                "story_client_uid": story["client_uid"],
                "assignee_member_id": member["id"],
                "assignee_name": "ignored in favor of member id",
                "competency": "SA",
                "effort": 2,
                "sprint_index": 0,
                "week_index": 1,
            },
        ),
        201,
    )
    work_item = board["initiatives"][0]["work_items"][0]
    assert work_item["assignee_member_id"] == member["id"]
    assert work_item["assignee_name"] == "Иванов Иван"

    board = assert_ok(
        await api_client.raw.patch(
            f"{path}/team-boards/initiatives/{initiative['id']}",
            json={
                "expected_version": board["version"],
                "title": "Edited on team board",
                "initiative_type": "Командная тех. повестка",
                "comment": "Shared entity",
                "tags": ["E2E"],
                "effort_by_competency": {"SA": 5},
                "agreed": True,
                "sprint_index": 0,
                "week_index": 1,
            },
        )
    )
    approved = board["initiatives"][0]
    assert approved["agreed"] is True
    assert approved["approved_by"] == "admin"
    assert approved["approved_at"]
    shared = assert_ok(await api_client.get(f"{path}/pre-pi"))["initiatives"][0]
    assert shared["title"] == "Edited on team board"
    assert shared["executors"][0]["effort_by_competency"] == {"SA": 5.0}

    capacity = assert_ok(await api_client.get(f"{path}/capacity"))
    alpha = next(row for row in capacity["teams"] if row["team"] == "Команда Альфа")
    assert alpha["load_by_sprint"]["0"] == {"SA": 2.0}
    assert alpha["load_by_week"]["0"]["1"] == {"SA": 2.0}

    program = assert_ok(
        await api_client.put(
            f"{path}/program-board",
            json={
                "connections": [
                    {
                        "client_uid": "team-command-edge",
                        "source": {"kind": "w", "ref": work_item["client_uid"]},
                        "target": {"kind": "c", "ref": "TEAM-CMD-1"},
                    }
                ]
            },
        )
    )

    member_cascade = await api_client.raw.request(
        "DELETE",
        f"{path}/capacity/members/{member['id']}",
        json={"expected_version": program["version"], "confirm_cascade": False},
    )
    assert member_cascade.status_code == 409
    assert member_cascade.json()["detail"]["code"] == "cascade_confirmation_required"
    capacity = assert_ok(
        await api_client.raw.request(
            "DELETE",
            f"{path}/capacity/members/{member['id']}",
            json={"expected_version": program["version"], "confirm_cascade": True},
        )
    )
    assert next(row for row in capacity["teams"] if row["team"] == "Команда Альфа")[
        "members"
    ] == []
    cleared = assert_ok(await api_client.get(f"{path}/team-boards"))["initiatives"][0][
        "work_items"
    ][0]
    assert cleared["assignee_member_id"] is None
    assert cleared["assignee_name"] == ""

    story_cascade = await api_client.raw.request(
        "DELETE",
        f"{path}/team-boards/initiatives/{initiative['id']}/stories/{story['id']}",
        json={"expected_version": capacity["version"], "confirm_cascade": False},
    )
    assert story_cascade.status_code == 409
    deleted = assert_ok(
        await api_client.raw.request(
            "DELETE",
            f"{path}/team-boards/initiatives/{initiative['id']}/stories/{story['id']}",
            json={"expected_version": capacity["version"], "confirm_cascade": True},
        )
    )
    assert deleted["initiatives"][0]["stories"] == []
    assert deleted["initiatives"][0]["work_items"] == []
    assert assert_ok(await api_client.get(f"{path}/program-board"))["connections"] == []

    stale = await api_client.raw.patch(
        f"{path}/team-boards/initiatives/{initiative['id']}",
        json={"expected_version": capacity["version"], "agreed": False},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    current_version = deleted["version"]
    alpha = next(
        row
        for row in assert_ok(await api_client.get(f"{path}/pre-pi"))["teams"]
        if row["name"] == "Команда Альфа"
    )
    goals = assert_ok(
        await api_client.raw.post(
            f"{path}/goals-board/goals",
            json={
                "expected_version": current_version,
                "team_id": alpha["id"],
                "title": "Atomic goal",
                "owner": "Иванов",
                "business_value": 89,
                "status": "planned",
                "category": "committed",
                "initiative_ids": [initiative["id"]],
            },
        ),
        201,
    )
    goal = goals["goals"][0]
    assert goal["id"]
    assert goal["team_id"] == alpha["id"]
    assert goal["initiative_ids"] == [initiative["id"]]
    assert goals["version"] == current_version + 1

    link_change = await api_client.raw.patch(
        f"{path}/goals-board/goals/{goal['id']}",
        json={
            "expected_version": goals["version"],
            "title": "Atomic goal",
            "initiative_ids": [],
            "confirm_cascade": False,
        },
    )
    assert link_change.status_code == 409
    assert link_change.json()["detail"]["code"] == "cascade_confirmation_required"

    goals = assert_ok(
        await api_client.raw.patch(
            f"{path}/goals-board/goals/{goal['id']}",
            json={
                "expected_version": goals["version"],
                "title": "Atomic goal edited",
                "initiative_ids": [],
                "confirm_cascade": True,
            },
        )
    )
    assert goals["goals"][0]["title"] == "Atomic goal edited"
    assert goals["goals"][0]["initiative_ids"] == []

    deleted_goals = assert_ok(
        await api_client.raw.request(
            "DELETE",
            f"{path}/goals-board/goals/{goal['id']}",
            json={"expected_version": goals["version"]},
        )
    )
    assert goal["id"] not in {row["id"] for row in deleted_goals["goals"]}

    risks = assert_ok(
        await api_client.raw.post(
            f"{path}/risks-board/risks",
            json={
                "expected_version": deleted_goals["version"],
                "scope": "team",
                "team_id": alpha["id"],
                "description": "Atomic risk",
                "probability": 4,
                "impact_level": 5,
                "roam": "owned",
            },
        ),
        201,
    )
    risk = risks["risks"][0]
    assert risk["team_id"] == alpha["id"]
    assert risk["criticality"] == 20
    assert risk["criticality_label"] == "critical"
    assert risk["roam"] == "owned"

    risks = assert_ok(
        await api_client.raw.patch(
            f"{path}/risks-board/risks/{risk['id']}/roam",
            json={"expected_version": risks["version"], "roam": "mitigated"},
        )
    )
    assert risks["risks"][0]["roam"] == "mitigated"

    risks = assert_ok(
        await api_client.raw.patch(
            f"{path}/risks-board/risks/{risk['id']}/status",
            json={"expected_version": risks["version"], "status": "closed"},
        )
    )
    assert risks["risks"][0]["status"] == "closed"


@pytest.mark.asyncio
async def test_pre_pi_regulatory_agenda_buckets_legal_owner_as_common(api_client):
    cycle = assert_ok(
        await api_client.post(
            "/pi-cycles",
            json={"year": 2033, "quarter": "Q2", "sprint_count": 3},
        ),
        201,
    )
    path = f"/pi-cycles/{cycle['id']}"
    assert_ok(
        await api_client.put(
            f"{path}/setup",
            json={
                "start_date": "2033-04-05",
                "sprint_count": 3,
                "pirs": [{"name": "ПИР", "date": "2033-04-19"}],
                "teams": [
                    {"tribe": "Регрессия", "name": "Legal", "team_type": "Agile", "competencies": ["SA", "DEV"]},
                    {"tribe": "Регрессия", "name": "Команда Альфа", "team_type": "Agile", "competencies": ["SA", "DEV", "QA"]},
                ],
                "goals": ["Цель"],
                "tags": ["REG"],
            },
        )
    )
    # Ёмкость владельцев досок — чтобы знаменатели процентов были ненулевыми.
    assert_ok(
        await api_client.put(
            f"{path}/capacity",
            json={
                "teams": [
                    {
                        "tribe": "Регрессия",
                        "team": "Legal",
                        "members": [
                            {"client_uid": "legal-member", "full_name": "Legal специалист", "competency": "DEV", "rate": 1}
                        ],
                    },
                    {
                        "tribe": "Регрессия",
                        "team": "Команда Альфа",
                        "members": [
                            {"client_uid": "reg-member", "full_name": "Регулятор", "competency": "DEV", "rate": 1}
                        ],
                    }
                ]
            },
        )
    )
    # Две регуляторные инициативы типа «Требования законодательства»:
    #   владелец Legal  → бакет «общая» (100),
    #   владелец Альфа  → бакет «командная» (30).
    # LEGAL остаётся владельцем первой задачи, но ресурсы вводит владелец доски — Альфа.
    assert_ok(
        await api_client.put(
            f"{path}/pre-pi",
            json={
                "initiatives": [
                    {
                        "issue_key": "REG-LEGAL",
                        "title": "Регула (Legal)",
                        "owner_team": "Legal",
                        "owner_tribe": "Регрессия",
                        "initiative_type": "Требования законодательства",
                        "status": "planned",
                        "pre_planned": True,
                        "executors": [
                            {"team": "Команда Альфа", "tribe": "Регрессия", "effort_by_competency": {"DEV": 100}}
                        ],
                    },
                    {
                        "issue_key": "REG-TEAM",
                        "title": "Регула (Альфа)",
                        "owner_team": "Команда Альфа",
                        "owner_tribe": "Регрессия",
                        "initiative_type": "Требования законодательства",
                        "status": "planned",
                        "pre_planned": True,
                        "executors": [
                            {"team": "Команда Альфа", "tribe": "Регрессия", "effort_by_competency": {"DEV": 30}}
                        ],
                    },
                ]
            },
        )
    )

    pre_pi = assert_ok(await api_client.get(f"{path}/pre-pi"))
    alpha_id = next(team["id"] for team in pre_pi["teams"] if team["name"] == "Команда Альфа")
    legal_id = next(team["id"] for team in pre_pi["teams"] if team["name"] == "Legal")

    alpha_metrics = pre_pi["capacity"]["teams"][alpha_id]
    reg = alpha_metrics["reg_agenda"]
    assert reg["common_effort"] == 100.0  # фактический владелец Legal → «общая»
    assert reg["team_effort"] == 30.0  # фактический владелец Альфа → «командная»
    assert reg["total_effort"] == 130.0
    assert reg["total_percent"] == round(130.0 / alpha_metrics["available_capacity"] * 100, 1)

    # Legal владеет задачей, но не доской: нагрузка относится на Альфу.
    assert pre_pi["capacity"]["teams"][legal_id]["reg_agenda"]["total_effort"] == 0.0

    # Верхнеуровневый (overall) блок и независимость от техповестки.
    assert pre_pi["reg_agenda"]["common_effort"] == 100.0
    assert pre_pi["reg_agenda"]["team_effort"] == 30.0
    assert pre_pi["reg_agenda"]["total_effort"] == 130.0
    assert pre_pi["tech_agenda"]["total_effort"] == 0.0
