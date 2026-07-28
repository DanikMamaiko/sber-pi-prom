from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _last_function(source: str, name: str, next_name: str) -> str:
    start = source.rindex(f"function {name}(){{")
    return source[start : source.index(f"function {next_name}", start)]


def test_goals_view_keeps_prototype_layout_with_backend_commands():
    source = FRONTEND.read_text(encoding="utf-8")
    view = _last_function(source, "viewGoals", "bindGoals")
    bind = _last_function(source, "bindGoals", "bindGoalRowDrag")

    assert source.count("function viewGoals(){") == 1
    assert source.count("function bindGoals(){") == 1
    assert 'id="goalFilterStatus"' not in view
    assert 'id="goalAddTeam"' not in view
    assert "data-goal-edit" not in view
    assert "data-goal-del" not in view
    assert "🎯 " in view
    assert "🏁 " in view
    assert ">⠿</span>" in view
    assert "data-goal-field-id" in view
    assert "goalsBoardCommand" in bind


def test_risks_view_keeps_prototype_navigation_and_fields():
    source = FRONTEND.read_text(encoding="utf-8")
    view = _last_function(source, "viewRisks", "bindRisks")
    bind = _last_function(source, "bindRisks", "riskPayloadFromModal")
    modal_start = source.rindex("function openRiskModal(riskId){")
    modal = source[modal_start : source.index("function deleteRiskUi", modal_start)]

    assert source.count("function viewRisks(){") == 1
    assert source.count("function bindRisks(){") == 1
    assert "Общие риски" in view
    assert "Командные риски" in view
    assert 'class="plus" id="riskAdd"' in view
    assert "riskFilterScope" not in view
    assert "riskFilterStatus" not in view
    assert "data-risk-tribe-id" in bind
    assert "data-rt-share" in bind
    assert "risksBoardCommand" in bind

    for field in ("rm_desc", "rm_owner", "rm_impact", "rm_control", "rm_plan"):
        assert f'id="{field}"' in modal
    for field in ("rm_scope", "rm_probability", "rm_impact_level", "rm_due", "rm_status", "rm_roam"):
        assert f'id="{field}"' not in modal
