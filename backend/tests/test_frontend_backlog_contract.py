from _frontend_source import frontend_source


def _source() -> str:
    return frontend_source()


def test_backlog_has_one_backend_read_model_and_no_browser_business_copy():
    source = _source()

    for forbidden in (
        "state.tribeBacklog",
        "seedBacklogDemo",
        "seedSbolBacklogDemo",
        "backlogBoardPayload",
        "persistBacklogBoard",
        "queueBacklogSync",
        "flushBacklogSync",
        "backlogBackendAdopted",
    ):
        assert forbidden not in source

    assert "let backlogBoard=null;" in source
    assert "applyBacklogBoard(await cycleApi(backlogScopedPath('/backlog-board',id)))" in source
    assert "cycle_id=${encodeURIComponent(backendId)}" in source


def test_each_backlog_action_uses_a_dedicated_command_and_server_response():
    source = _source()
    start = source.index("function backlogMutation(")
    mutation = source[start : source.index("function cycleApiPayload", start)]

    assert mutation.count("cycleApi(") == 1
    assert "backlogScopedPath(path)" in mutation
    assert "expected_version:backlogBoard.version" in mutation
    assert "applyBacklogBoard(await backlogMutation" in source
    assert "'/backlog-board/items','POST'" in source
    assert "'PATCH',payload" in source
    assert "'DELETE',{},true" in source
    assert "'/backlog-board/order','PUT'" in source
    assert "'/backlog-board/dispatch','POST'" in source


def test_backlog_bundle_has_no_legacy_api_or_frontend_effort_calculation():
    source = _source()
    start = source.index("function viewBacklog(){")
    end = source.index("/* =====================================================================\n   БЮДЖЕТИРОВАНИЕ", start)
    backlog = source[start:end]

    assert "/initiatives/from-backlog" not in source
    assert "/pi-cycles/${cycleBackendIds[target]}/backlog/dispatch" not in source
    assert "issueTotalEffort(it)" not in backlog
    assert "row.total_effort" in source


def test_backlog_keeps_the_prototype_structure_and_empty_states():
    source = _source()
    start = source.index("function viewBacklogBoard(")
    view = source[start : source.index("function backlogQuarterCell", start)]

    for marker in (
        "Выбор трайба",
        "Добавить по № Issue",
        "Отправить на Pre PI Planning",
        "Бэклог пуст — добавьте инициативу по № Issue.",
        "Команда-исполнитель и компетенции",
        "prep-wrap",
        "bk-table",
    ):
        assert marker in view
