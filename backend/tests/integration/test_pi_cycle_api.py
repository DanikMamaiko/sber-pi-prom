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
                "status": "planned",
                "pre_planned": True,
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
                                "team": "Команда Альфа",
                                "effort_by_competency": {"SA": 1},
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
                        "team": "Команда Альфа",
                        "tribe": "Регрессия",
                        "effort_by_competency": {"SA": 1},
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
    assert assert_ok(await api_client.get(f"/pi-cycles/{cycle_id}/pre-pi"))["initiatives"][0]["executors"][0]["team"] == "Команда Альфа"

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
        "message": "Aggregate was changed by another editor",
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
    repeated = await api_client.post(
        "/backlog-board/dispatch",
        json={"tribe": "Регрессия", "target_year": 2033, "target_quarter": "Q3"},
    )
    assert repeated.status_code == 422
    assert assert_ok(await api_client.get("/backlog-board"))["version"] == repeat_version

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
    assert cycle_unlinked["version"] == cycle_after["version"] + 1


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
                                "target_initiative_id": second["id"],
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
    assert edited_first["total_estimate"] == 7
    attraction = edited_first["executors"][0]["attractions"][0]
    assert attraction["id"]
    assert attraction["approval_status"] == "pending"
    assert attraction["visual_state"] == "purple"

    moved_second = assert_ok(
        await api_client.post(
            f"{path}/pre-pi/initiatives/{second['id']}/move",
            json={"target_block": "planned"},
        )
    )
    moved_first = assert_ok(
        await api_client.post(
            f"{path}/pre-pi/initiatives/{first['id']}/move",
            json={"target_block": "planned", "before_id": second["id"]},
        )
    )
    assert [row["issue_key"] for row in moved_first["planned"]] == ["CMD-1", "CMD-2"]
    assert [row["sort_order"] for row in moved_first["planned"]] == [0, 1]

    submitted = assert_ok(
        await api_client.post(
            f"{path}/pre-pi/submit",
            json={"teams": [{"tribe": "Регрессия", "name": "Команда Альфа"}]},
        )
    )
    assert submitted["board_added"] == 1
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
