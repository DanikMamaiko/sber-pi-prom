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


def test_team_board_forms_close_only_after_successful_commands():
    boards = source("team-boards.js")
    create_start = boards.index("$('#m_save').onclick=async()=>{")
    create_handler = boards[create_start : boards.index("/* ---- Модальное окно Истории", create_start)]
    save_start = boards.index("$('#w_save').onclick=async()=>{")
    save_handler = boards[save_start : boards.index("/* ---- Геометрия краёв", save_start)]

    assert create_handler.index("const created=await runBoardCommand") < create_handler.index("root.innerHTML='';")
    assert "if(!created)return;" in create_handler
    assert "if(await runBoardCommand" in save_handler
    assert save_handler.index("if(await runBoardCommand") < save_handler.index("root.innerHTML='';")


def test_capacity_member_is_created_from_validated_modal():
    boards = source("team-boards.js")

    assert "function openCapacityMemberModal(t)" in boards
    assert "if(!fullName)" in boards
    assert "full_name:fullName" in boards
    assert "full_name:''" not in boards
    assert "addCap.onclick=()=>openCapacityMemberModal(t)" in boards
