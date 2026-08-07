from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(name: str) -> str:
    return (ROOT / "frontend" / "js" / name).read_text(encoding="utf-8")


def css_source(name: str) -> str:
    return (ROOT / "frontend" / "css" / name).read_text(encoding="utf-8")


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


def test_team_board_commands_refresh_dependent_projections():
    api = source("api.js")
    handler_start = api.index("async function teamBoardCommand(path")
    handler = api[handler_start : api.index("function capacityCycleYear", handler_start)]
    refresh = "await refreshCycleProjections(id,{capacity:true,programBoard:true,risks:true})"

    assert refresh in handler
    assert handler.index(refresh) < handler.index("return aggregate;")


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


def test_team_board_story_hierarchy_creates_program_board_connections():
    api = source("api.js")
    boards = source("team-boards.js")

    assert "if(endpoint.kind==='g')return {kind:'g',uid:endpoint.ref};" in api
    assert "if(ep.kind==='g'){" in api
    assert "return {kind:'story',id:story._backendId};" in api
    assert "source:{kind:'initiative',id:iss._backendId}" in boards
    assert "target:{kind:'story',id:createdStory._backendId}" in boards
    assert "source:{kind:'story',id:parentStory._backendId}" in boards
    assert "target:{kind:'work_item',id:item._backendId}" in boards
    assert 'data-link-kind="c" data-link-key="${esc(iss.id)}"' in source("program-board.js")
    assert 'data-link-kind="g" data-link-key="${esc(sy.uid)}"' in source("program-board.js")
    assert ".sticker .c-link{display:block;width:max-content;max-width:100%}" in css_source("styles.css")
    assert "kind==='g' ? {kind:'g',uid:key}" in boards
    assert "scope.querySelector(`.story[data-story-uid=" in boards
    assert "e.target.closest('.x,.c-link')" in boards
    assert "e.target.closest('.x,.s-link')" in boards
    assert "el.closest('.sticker,.story,.white')" in boards


def test_team_board_subtask_modal_does_not_send_role_as_assignee_name():
    boards = source("team-boards.js")

    assert "function boardAssigneeDatalist(roster)" in boards
    assert ".filter(p=>p.fio)" in boards
    assert "label=\"${esc(p.role)}\"" in boards
    assert "function boardAssigneePayload(roster,name,role,validRoles)" in boards
    assert "roleTokens.has(assigneeName.toUpperCase())?'':assigneeName" in boards
    assert "assignee_member_id:assignee.assignee_member_id,assignee_name:assignee.assignee_name" in boards


def test_team_board_sync_error_toast_includes_backend_reason():
    api = source("api.js")

    start = api.index("function reportTeamBoardsSyncError(error)")
    handler = api[start : api.index("async function persistTeamBoardsCycle", start)]

    assert "replace(/^Задача\\s+\\S+:\\s*/,'')" in handler
    assert "`${base} ${reason.charAt(0).toUpperCase()+reason.slice(1)}`" in handler
    assert "на сервере" not in handler
    assert "Причина:" not in handler
    assert "timeout:8000" in handler


def test_team_board_prevents_decomposition_after_parent_issue():
    boards = source("team-boards.js")

    assert "function boardPeriodAfter(sprint,week,parentSprint,parentWeek)" in boards
    assert "function decompositionAfterIssue(iss,sprint,week)" in boards
    assert "не может быть запланирована позже главной задачи" in boards
    assert "warnDecompositionAfterIssue('История')" in boards
    assert "warnDecompositionAfterIssue('Подзадача')" in boards
    assert "Главная задача не может быть запланирована раньше своих историй или подзадач" in boards
    assert "if(decompositionAfterIssue(iss,+target,targetWeek))" in boards
    assert "if(decompositionAfterIssue(iss,white.sprint,white.week))" in boards
    assert "if(decompositionAfterIssue(iss,f.sprint,f.week))" in boards


def test_capacity_member_is_created_from_validated_modal():
    boards = source("team-boards.js")

    assert "function openCapacityMemberModal(t)" in boards
    assert "if(!fullName)" in boards
    assert "full_name:fullName" in boards
    assert "full_name:''" not in boards
    assert "addCap.onclick=()=>openCapacityMemberModal(t)" in boards
