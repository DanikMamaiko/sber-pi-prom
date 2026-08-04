from _frontend_source import frontend_source


def test_pi_business_data_is_not_persisted_in_browser_storage():
    source = frontend_source()

    assert "localStorage" not in source
    assert "const out={storageVersion:STORAGE_VERSION,ui:state.ui,budgets:state.budgets};" in source
    assert "cycles: { '2026-Q1'" not in source


def test_active_pi_data_boot_is_auth_first_and_uses_permission_scoped_read_models():
    source = frontend_source()
    boot = source[source.index("async function boot(){") : source.index("boot();", source.index("async function boot(){"))]

    assert "currentUser=await authRequest('/auth/me')" in boot
    assert "await bootAuthenticated();" in boot
    assert "await loadPiDataViews();" not in boot
    assert "if(hasPermission('pi_data:read'))await loadPiDataView(id);" in source
    assert "async function loadAuthorizedCycle(id)" in source
    assert "loadCycleSetups" not in boot
    assert "normalize();" not in boot
    assert "function piDataCommand(" in source
    assert "function applyPiDataView(" in source
    assert "state.ui.tab!=='data'" in source


def test_pi_data_legacy_implementations_cannot_return_to_active_bundle():
    source = frontend_source()

    forbidden_legacy_symbols = (
        "legacyViewData",
        "legacyBindData",
        "commandViewDataV1",
        "commandBindDataV1",
        "commitDataInputs",
        "cycleSetupPayload",
        "applyCycleSetup",
        "persistCycleSetup",
        "loadCycleSetups",
    )

    for symbol in forbidden_legacy_symbols:
        assert symbol not in source


def test_active_pi_data_view_keeps_prototype_layout_contract():
    source = frontend_source()
    start = source.rindex("function viewData(){")
    view = source[start : source.index("function piDataFormPayload(){", start)]

    assert 'id=\"saveData\"' in view
    assert 'id=\"editData\"' in view
    assert 'id=\"addPir\"' in view
    assert 'id=\"addTeam\"' in view
    assert 'id=\"addGoal\"' in view
    assert 'id=\"addTag\"' in view
    assert "Расписание backend" not in view
    assert "data-save-pir" not in view
