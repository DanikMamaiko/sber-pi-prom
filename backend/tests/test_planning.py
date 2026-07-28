from datetime import date

import pytest
from pydantic import ValidationError

from app.models.pi_cycle import PiCycle, PiCycleCapacityMember
from app.schemas.pi_cycle import (
    BacklogBoardWrite,
    BacklogDispatchWrite,
    CapacityWrite,
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
