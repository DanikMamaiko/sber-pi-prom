from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(name: str) -> str:
    return (ROOT / "frontend" / "js" / name).read_text(encoding="utf-8")


def test_program_board_uses_server_projection_and_atomic_commands():
    frontend = "".join(source(name) for name in ("program-board.js", "team-boards.js", "api.js", "state.js", "app.js"))

    assert "programBoardViews" in frontend
    assert "programBoardMoveInitiative" in frontend
    assert "programBoardCommand('/connections','POST'" in frontend
    assert "queueProgramBoardSync" not in frontend
    assert "programBoardPayload" not in frontend
    assert "persistProgramBoardCycle" not in frontend
    assert "computeSprints()" not in source("program-board.js")


def test_program_board_business_data_is_not_saved_in_browser_storage():
    state_source = source("state.js")

    assert "localStorage" not in state_source
    save_source = state_source[state_source.index("function save("):state_source.index("function save(") + 700]
    assert "state.cycles" not in save_source


def test_program_board_renders_unscheduled_initiatives():
    board = source("program-board.js")

    assert "const hasUnscheduled=(board.cards||[]).some" in board
    assert "${hasUnscheduled?'<th class=\"sp pb-unscheduled-head\">Не назначено</th>':''}" in board
    assert "card.sprint_index===null||card.sprint_index===undefined" in board
    assert 'class="pb-cell pb-unscheduled"' in board
    assert "if(hasUnscheduled){" in board


def test_program_board_moves_refresh_team_board_and_capacity():
    api = source("api.js")
    handler_start = api.index("async function programBoardMoveInitiative")
    handler = api[handler_start : api.index("function programBoardEndpointPayload", handler_start)]
    refresh = "await refreshCycleProjections(id,{teamBoards:true,capacity:true})"

    assert refresh in handler
    assert handler.index(refresh) < handler.index("return aggregate;")


def test_program_board_sticker_zoom_is_ui_only_and_hover_is_readable():
    board = source("program-board.js")
    state = source("state.js")
    styles = (ROOT / "frontend" / "css" / "styles.css").read_text(encoding="utf-8")

    assert "pbStickerZoom:1" in state
    assert 'id="pbStickerZoomOut"' in board
    assert 'id="pbStickerZoomIn"' in board
    assert "save(false)" in board
    assert "--pb-sticker-zoom" in styles
    assert "--pb-sticker-hover-scale" in styles
    assert "scale(var(--pb-sticker-hover-scale,1.25))" in styles
