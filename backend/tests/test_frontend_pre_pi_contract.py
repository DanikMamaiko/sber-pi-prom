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
    # Номер привлекаемой инициативы вводится вручную (стикером), а не из списка.
    assert "ID Issue из JSW" in section
    assert "— выберите инициативу —" not in section


def test_pre_pi_executor_editor_uses_active_cycle_competencies():
    source = frontend_source()

    assert "kind==='bk' ? backlogTeamCompetencies(ex.team) : teamComps(ex.team)" in source
    assert "const current=issueExecutors(iss)[0]" in source
    assert "function boardOwnerExecutorView(iss)" in source
    assert "Компетенции команды владельца" in pre_pi_source()
    assert "+ Команда-исполнитель" not in pre_pi_source()
    assert "data-pi-execadd" not in pre_pi_source()


def test_backlog_managed_pre_pi_fields_are_rendered_read_only():
    source = frontend_source()
    section = pre_pi_source()

    assert "lockedFields:Array.isArray(row.locked_fields)?row.locked_fields:[]" in source
    assert "function prepFieldLocked" in section
    assert "sourceField:'customer_priority'" in section
    assert "sourceField:'team_priority'" in section
    assert "sourceField:'product'" in section
    assert "sourceField:'owner_team_id'" in section
    assert "sourceField:'initiative_type'" in section
    assert "sourceField:'tshirt_size'" in section
    assert "prepFieldLocked(i,'effort_by_competency')" in section
    assert "ownerCompsBlockHTML(i,'pi',effortLocked" in section
    assert "Поля, синхронизируемые из вкладки «Бэклог», недоступны для редактирования" in section
    assert "🔒" not in section


def test_pre_pi_attraction_requests_are_stacked_in_their_column():
    section = pre_pi_source()

    assert 'class="attr-list"' in section
    assert 'class="attr-request' in section
    assert "effortByCompetency" in section
    assert "resourceEstimate" in section
    assert "Ресурсы задачи" in section


def test_pre_pi_total_estimate_shows_owner_and_attraction_breakdown():
    source = frontend_source()
    section = pre_pi_source()

    assert "function prepEffortSummaryHTML" in section
    assert "ownerEstimate" in section
    assert "attractionEstimate" in section
    assert "pendingAttractionEstimate" in section
    assert "Свои ${owner} + привлечённые ${attracted}" in section
    assert "ownerEstimate:+row.owner_estimate" in source
    assert "attractionEstimate:+row.attraction_estimate" in source
    assert "pendingAttractionEstimate:+row.pending_attraction_estimate" in source


def test_pre_pi_attraction_excludes_the_current_board_owner():
    section = pre_pi_source()

    assert "team._teamId!==host.teamId" in section
    assert "team.name!==host.team" in section
    assert "Нельзя привлекать команду-владельца текущей доски" in section


def test_pre_pi_submit_refreshes_dependent_tabs_before_render():
    section = pre_pi_source()
    handler_start = section.index("async function prepSubmitToBoards(targets)")
    handler = section[handler_start : section.index("function openAttractionModal", handler_start)]

    refresh = "await refreshCycleProjections(id,{teamBoards:true,capacity:true,programBoard:true,risks:true})"
    assert refresh in handler
    assert handler.index(refresh) < handler.index("save();render();")


def test_pre_pi_commands_refresh_dependent_cycle_projections():
    source = frontend_source()
    handler_start = source.index("async function prePiCommand(path")
    handler = source[handler_start : source.index("async function loadPrePiCycles", handler_start)]
    refresh = "await refreshCycleProjections(id,{goals:true,teamBoards:true,capacity:true,programBoard:true,risks:true})"

    assert "function refreshCycleProjections" in source
    assert refresh in handler
    assert handler.index(refresh) < handler.index("render();")
