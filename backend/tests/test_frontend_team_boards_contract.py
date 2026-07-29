from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(name: str) -> str:
    return (ROOT / "frontend" / "js" / name).read_text(encoding="utf-8")


def test_team_boards_use_versioned_backend_commands_and_server_capacity():
    api = source("api.js")
    boards = source("team-boards.js")
    utils = source("utils.js")

    for route in (
        "/team-boards${path}",
        "/capacity${path}",
        "/work-items",
        "/stories",
        "/members",
    ):
        assert route in api or route in boards
    assert "cycleMutation" in api
    assert "expected_version" in api
    assert "load_by_sprint" in api
    assert "load_by_week" in api
    assert "cached.weeks" in utils
    assert "planned=sprint.workdays" not in utils
    assert "rangeWorkdaysInPeriod" not in utils
    assert "personVacation" not in utils


def test_team_boards_do_not_persist_business_data_in_browser_or_use_demo_rosters():
    state = source("state.js")
    boards = source("team-boards.js")
    utils = source("utils.js")

    assert "localStorage" not in state + boards + utils
    assert "persistedTeamBoardSnapshots" not in state
    assert "persistedCapacitySnapshots" not in state
    assert "DEFAULT_TEAM_COMPS" not in state + utils
    assert "Демо-список" not in state
    assert "return t && Array.isArray(t.comps) ? t.comps.slice() : []" in utils
    assert "sessionStorage.setItem('piPlanning'" in state
    assert "const out={storageVersion:STORAGE_VERSION,ui:state.ui,budgets:state.budgets}" in state
