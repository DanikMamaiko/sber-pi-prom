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

    assert "pb-unscheduled-head\">Не назначено" in board
    assert "card.sprint_index===null||card.sprint_index===undefined" in board
    assert 'class="pb-cell pb-unscheduled"' in board
