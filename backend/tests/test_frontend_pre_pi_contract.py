from _frontend_source import frontend_source


def pre_pi_source() -> str:
    source = frontend_source()
    start = source.index("ВКЛАДКА 2 — Pre PI Planning")
    end = source.index("ВКЛАДКА 2 — Цели", start)
    return source[start:end]


def test_pre_pi_has_one_command_driven_frontend_implementation():
    source = frontend_source()
    section = pre_pi_source()
    for legacy in (
        "rolePlanTotal",
        "roleFact",
        "teamCalendarCap",
        "teamPlannedCap",
        "techAgendaSum",
        "capPanelData",
        "validateDevFuncInitiatives",
        "seedSbolPrepDemo",
        "flushPrePiSync",
        "prePiPayload",
    ):
        assert legacy not in source
    assert "prePiCapacityPanelHTML" in section
    assert "prePiCommand(path" in source
    assert "target_block" in section


def test_pre_pi_does_not_optimistically_mutate_business_state():
    section = pre_pi_source()
    assert "state.issues.splice" not in section
    assert "state.issues.push" not in section
    assert "iss.prePlanned=" not in section
    assert "queuePrePiSync" not in section
    assert "issueTotalEffort(i)" not in section


def test_pre_pi_uses_only_backend_entities_for_executors_and_attractions():
    section = pre_pi_source()
    assert "team_id" in section
    assert "target_initiative_id" in section
    assert "target_team_id" in section
    assert "— выберите инициативу —" in section


def test_pre_pi_executor_editor_uses_active_cycle_competencies():
    source = frontend_source()

    assert "kind==='bk' ? backlogTeamCompetencies(ex.team) : teamComps(ex.team)" in source
    assert "kind==='bk' ? backlogTeamCompetencies(ex.team) : teamCompsFor(ex.team)" not in source
