from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.pi_cycle import Initiative, PiCycle, PiCycleCapacityMember, PiGoal
from app.schemas.pi_cycle import (
    BacklogBoardWrite,
    BacklogDispatchWrite,
    CapacityWrite,
    CapacityMemberCreate,
    CapacityMemberUpdate,
    GoalsWrite,
    PiCycleCreate,
    PiCycleSetupWrite,
    PiCycleUpdate,
    PrePiWrite,
    PrePiSubmitWrite,
    ProgramBoardWrite,
    RisksWrite,
    TeamBoardsWrite,
)
from app.services.planning import compute_sprints
from app.services.capacity import calculate_member_capacity
from app.services.pre_pi import (
    LEGAL_OWNER_TEAM,
    REG_TYPE,
    _regulatory_by_team,
    _scope_metrics,
    validate_status_transition,
)
from app.services.goals import _sync_goal_to_initiatives


def test_compute_sprints_uses_two_week_periods():
    cycle = PiCycle(year=2026, quarter="Q1", start_date=date(2026, 7, 6), sprint_count=2)

    sprints = compute_sprints(cycle)

    assert len(sprints) == 2
    assert sprints[0].start_date == date(2026, 7, 6)
    assert sprints[0].end_date == date(2026, 7, 19)
    assert sprints[1].start_date == date(2026, 7, 20)
    assert sprints[1].end_date == date(2026, 8, 2)


def test_pi_cycle_write_schema_rejects_legacy_snapshot():
    with pytest.raises(ValidationError):
        PiCycleCreate(
            year=2026,
            quarter="Q1",
            start_date=date(2026, 7, 6),
            sprint_count=20,
            snapshot={"pi": {"startDate": "2026-07-06", "sprintCount": 20}},
        )


def test_pi_cycle_schema_matches_frontend_sprint_limit():
    with pytest.raises(ValidationError):
        PiCycleUpdate(sprint_count=21)


def test_pi_cycle_setup_accepts_the_prototype_contract():
    setup = PiCycleSetupWrite(
        expected_version=0,
        start_date=date(2026, 7, 6),
        sprint_count=6,
        pirs=[{"name": "ПИР8", "date": "2026-08-08"}],
        teams=[
            {
                "tribe": "Розничный бизнес",
                "name": "СБОЛ",
                "team_type": "Agile",
                "excluded_from_goals": False,
                "competencies": ["SA", "FE", "BE", "DES"],
            }
        ],
        goals=["Повысить конверсию"],
        tags=["Клиентский путь"],
    )

    assert setup.pirs[0].date == date(2026, 8, 8)
    assert setup.teams[0].competencies == ["SA", "FE", "BE", "DES"]


def test_backlog_board_accepts_the_prototype_contract():
    board = BacklogBoardWrite(
        expected_version=0,
        items=[
            {
                "tribe": "Розничный бизнес",
                "issue_key": "SBOL-3001",
                "title": "Развитие переводов",
                "target_year": 2026,
                "target_quarter": "Q1",
                "systems": ["СБОЛ", "КСШ"],
                "executors": [
                    {
                        "team": "СБОЛ",
                        "effort_by_competency": {"SA": 4, "FE": 8},
                    }
                ],
            }
        ]
    )

    assert board.items[0].executors[0].effort_by_competency["FE"] == 8


def test_backlog_dispatch_requires_server_selection_dimensions():
    with pytest.raises(ValidationError):
        BacklogDispatchWrite(expected_version=0, tribe="", target_year=2026, target_quarter="Q5")


def test_pre_pi_accepts_prototype_fields_and_attractions():
    payload = PrePiWrite(
        expected_version=0,
        initiatives=[
            {
                "issue_key": "SBOL-3001",
                "title": "Развитие переводов",
                "owner_team": "СБОЛ",
                "owner_tribe": "Розничный бизнес",
                "customer_priority": "1",
                "team_priority": "2",
                "goal_text": "Повысить конверсию",
                "pre_planned": True,
                "executors": [
                    {
                        "team": "СБОЛ",
                        "tribe": "Розничный бизнес",
                        "effort_by_competency": {"SA": 4, "FE": 8},
                        "attractions": [
                            {
                                "issue_key": "PLAT-42",
                                "team": "Платформа",
                                "sprint_index": 1,
                            }
                        ],
                    }
                ],
            }
        ]
    )

    initiative = payload.initiatives[0]
    assert initiative.pre_planned is True
    assert initiative.executors[0].attractions[0].sprint_index == 1


def test_goals_board_accepts_team_and_initiative_contract():
    payload = GoalsWrite(
        expected_version=0,
        goals=[
            {
                "tribe": "Розничный бизнес",
                "team": "СБОЛ",
                "issue_key": "SBOL-3001",
                "initiative_title": "Развитие переводов",
                "goal_text": "Повысить конверсию",
                "metric": "Конверсия",
                "current_value": "10%",
                "target_value": "15%",
            }
        ]
    )

    assert payload.goals[0].team == "СБОЛ"
    assert payload.goals[0].target_value == "15%"


def test_goal_sync_falls_back_to_legacy_initiative_relationship():
    initiative = Initiative(issue_key="SBOL-3001", title="Развитие переводов")
    goal = PiGoal(
        title="Повысить конверсию",
        product="СБОЛ",
        metric="Конверсия",
        current_value="10%",
        target_value="15%",
        hypothesis="Упростить путь",
        redesign="Новый экран",
        initiative=initiative,
    )

    _sync_goal_to_initiatives(goal)

    assert initiative.goal_text == "Повысить конверсию"
    assert initiative.product == "СБОЛ"
    assert initiative.metric == "Конверсия"
    assert initiative.current_value == "10%"
    assert initiative.target_value == "15%"
    assert initiative.hypothesis == "Упростить путь"
    assert initiative.redesign == "Новый экран"


def test_pre_pi_submit_requires_at_least_one_team():
    with pytest.raises(ValidationError):
        PrePiSubmitWrite(expected_version=0, teams=[])


def test_team_boards_accept_stories_and_work_items():
    payload = TeamBoardsWrite(
        expected_version=0,
        initiatives=[
            {
                "issue_key": "SBOL-3001",
                "on_board": True,
                "sprint_index": 1,
                "stories": [
                    {
                        "client_uid": "story-1",
                        "external_key": "SBOL-3001-S1",
                        "title": "История переводов",
                        "effort_by_competency": {"SA": 2, "FE": 5},
                        "sprint_index": 1,
                    }
                ],
                "work_items": [
                    {
                        "client_uid": "work-1",
                        "story_client_uid": "story-1",
                        "assignee_name": "Иванов",
                        "competency": "FE",
                        "effort": 3,
                        "sprint_index": 1,
                        "week_index": 0,
                    }
                ],
            }
        ]
    )

    board = payload.initiatives[0]
    assert board.stories[0].client_uid == "story-1"
    assert board.work_items[0].story_client_uid == "story-1"


def test_capacity_accepts_cycle_members_and_date_ranges():
    payload = CapacityWrite(
        expected_version=0,
        teams=[
            {
                "tribe": "Розничный бизнес",
                "team": "СБОЛ",
                "members": [
                    {
                        "client_uid": "person-1",
                        "full_name": "Иванов",
                        "competency": "SA",
                        "rate": 0.5,
                        "vacation_ranges": [
                            {"start": "2026-07-06", "end": "2026-07-07"}
                        ],
                        "ceremony_percent": 10,
                        "risk_percent": 5,
                        "efficiency": 0.9,
                    }
                ],
            }
        ]
    )

    assert payload.teams[0].members[0].vacation_ranges[0].start == date(2026, 7, 6)
    assert payload.teams[0].members[0].efficiency == 0.9


def test_capacity_member_rejects_blank_names_and_trims_valid_names():
    with pytest.raises(ValidationError):
        CapacityMemberCreate(
            expected_version=0,
            tribe="Розничный бизнес",
            team="СБОЛ",
            client_uid="person-blank",
            full_name="   ",
            competency="SA",
        )
    with pytest.raises(ValidationError):
        CapacityMemberUpdate(expected_version=0, full_name="   ")

    member = CapacityMemberCreate(
        expected_version=0,
        tribe="Розничный бизнес",
        team="СБОЛ",
        client_uid="person-trimmed",
        full_name="  Иванов Иван  ",
        competency="SA",
    )
    assert member.full_name == "Иванов Иван"


def test_capacity_formula_matches_prototype():
    cycle = PiCycle(
        year=2026,
        quarter="Q1",
        start_date=date(2026, 7, 6),
        sprint_count=1,
    )
    member = PiCycleCapacityMember(
        cycle_id=cycle.id,
        team_id=None,
        client_uid="person-1",
        full_name="Иванов",
        competency="SA",
        rate=0.5,
        vacation_ranges=[{"start": "2026-07-06", "end": "2026-07-07"}],
        extra_unavailable_ranges=[{"start": "2026-07-08", "end": "2026-07-08"}],
        ceremony_percent=10,
        risk_percent=10,
        efficiency=0.8,
    )

    calendar, available, sprints = calculate_member_capacity(member, cycle)

    assert calendar == pytest.approx(5)
    assert available == pytest.approx(2)
    assert sprints[0].vacation_days == 2
    assert sprints[0].extra_unavailable_days == 1


def test_pre_pi_status_transitions_are_server_owned():
    validate_status_transition("backlog", "planned")
    validate_status_transition("planned", "on_board")
    with pytest.raises(ValueError):
        validate_status_transition("backlog", "done")
    with pytest.raises(ValueError):
        validate_status_transition("on_board", "backlog")


def test_pre_pi_server_metrics_handle_zero_denominator_and_over_capacity():
    metrics = _scope_metrics(
        [
            {
                "team": "Команда Альфа",
                "calendar_capacity": 10,
                "available_capacity": 0,
                "planned_effort": 3,
                "available_by_competency": {"SA": 0},
                "planned_by_competency": {"SA": 3},
            }
        ],
        {"Команда Альфа": {"common": 2, "team": 1}},
    )
    assert metrics["over_capacity"] is True
    assert metrics["competencies"]["SA"]["over_capacity"] is True
    assert metrics["tech_agenda"]["total_percent"] is None


def test_regulatory_by_team_buckets_by_owner_and_attributes_by_executor():
    def exe(team, comps):
        return SimpleNamespace(team=SimpleNamespace(name=team), effort_by_competency=comps)

    def init(owner, executors, *, pre_planned=True, itype=REG_TYPE):
        return SimpleNamespace(
            pre_planned=pre_planned,
            initiative_type=itype,
            owner_team=SimpleNamespace(name=owner),
            executors=executors,
        )

    initiatives = [
        # Владелец Legal → бакет «общая»; исполняют X (100) и Y (50).
        init(LEGAL_OWNER_TEAM, [exe("Команда X", {"DEV": 100}), exe("Команда Y", {"DEV": 50})]),
        # Иной владелец → бакет «командная»; исполняет X (30).
        init("Розница", [exe("Команда X", {"DEV": 30})]),
        # Не запланирована — пропускается.
        init(LEGAL_OWNER_TEAM, [exe("Команда X", {"DEV": 10})], pre_planned=False),
        # Не регуляторный тип — пропускается.
        init(LEGAL_OWNER_TEAM, [exe("Команда X", {"DEV": 20})], itype="Развитие функционала"),
    ]
    reg = _regulatory_by_team(initiatives)
    assert reg["Команда X"] == {"common": 100.0, "team": 30.0}
    assert reg["Команда Y"] == {"common": 50.0, "team": 0.0}
    # Legal как владелец ничего не исполняет — на его строку усилие не ложится.
    assert LEGAL_OWNER_TEAM not in reg
    assert sum(v["common"] for v in reg.values()) == 150.0
    assert sum(v["team"] for v in reg.values()) == 30.0


def test_scope_metrics_reg_agenda_percent_and_zero_denominator():
    base_row = {
        "team": "Команда X",
        "calendar_capacity": 100,
        "available_capacity": 200,
        "planned_effort": 0,
        "available_by_competency": {"DEV": 200},
        "planned_by_competency": {"DEV": 0},
    }
    reg_by_team = {"Команда X": {"common": 50.0, "team": 30.0}}
    metrics = _scope_metrics([base_row], {}, reg_by_team)
    agenda = metrics["reg_agenda"]
    assert agenda["common_effort"] == 50.0
    assert agenda["team_effort"] == 30.0
    assert agenda["total_effort"] == 80.0
    assert agenda["common_percent"] == 25.0  # 50 / 200
    assert agenda["team_percent"] == 15.0  # 30 / 200
    assert agenda["total_percent"] == 40.0  # 80 / 200
    # Нулевой знаменатель → проценты None, абсолютные значения остаются.
    zero = _scope_metrics([{**base_row, "available_capacity": 0}], {}, reg_by_team)
    assert zero["reg_agenda"]["total_percent"] is None
    assert zero["reg_agenda"]["common_effort"] == 50.0


def test_program_board_accepts_endpoints_and_relative_bend():
    payload = ProgramBoardWrite(
        expected_version=0,
        connections=[
            {
                "client_uid": "connection-1",
                "source": {"kind": "w", "ref": "work-1"},
                "target": {"kind": "c", "ref": "SBOL-3001"},
                "bend": {"dx": 42.5, "dy": -18},
            }
        ]
    )

    connection = payload.connections[0]
    assert connection.source.kind == "w"
    assert connection.target.ref == "SBOL-3001"
    assert connection.bend.dx == 42.5


def test_program_board_rejects_unknown_endpoint_kind():
    with pytest.raises(ValidationError):
        ProgramBoardWrite(
            expected_version=0,
            connections=[
                {
                    "client_uid": "connection-1",
                    "source": {"kind": "story", "ref": "story-1"},
                    "target": {"kind": "c", "ref": "SBOL-3001"},
                }
            ]
        )


def test_risks_accept_general_and_shared_team_records():
    payload = RisksWrite(
        expected_version=0,
        risks=[
            {
                "client_uid": "risk-general-1",
                "scope": "general",
                "description": "Общий риск",
            },
            {
                "client_uid": "risk-team-1",
                "scope": "team",
                "team": {"tribe": "Розничный бизнес", "name": "СБОЛ"},
                "is_shared": True,
                "description": "Командный риск",
                "owner": "Иванов",
                "impact": "Высокое",
                "control_point": "ПИР",
                "mitigation_plan": "Снизить вероятность",
            },
        ]
    )

    assert payload.risks[0].scope == "general"
    assert payload.risks[1].team.name == "СБОЛ"
    assert payload.risks[1].is_shared is True


def test_risks_reject_unknown_scope_and_empty_description():
    with pytest.raises(ValidationError):
        RisksWrite(
            expected_version=0,
            risks=[
                {
                    "client_uid": "risk-1",
                    "scope": "project",
                    "description": "Риск",
                }
            ]
        )
    with pytest.raises(ValidationError):
        RisksWrite(
            expected_version=0,
            risks=[
                {
                    "client_uid": "risk-2",
                    "scope": "general",
                    "description": "",
                }
            ]
        )
