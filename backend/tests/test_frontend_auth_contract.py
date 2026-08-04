from _frontend_source import frontend_source


def test_frontend_boots_auth_first_and_uses_http_only_cookie_credentials():
    source = frontend_source()
    boot_start = source.index("async function boot(){")
    boot = source[boot_start : source.index("boot();", boot_start)]

    assert "renderAuthLoading();" in boot
    assert "currentUser=await authRequest('/auth/me')" in boot
    assert "appNavigation=await authRequest('/app/navigation')" in source
    assert "credentials:'include'" in source
    assert "localStorage" not in source
    assert "sessionStorage.setItem('sberpi" not in source


def test_unauthorized_response_returns_to_login_and_stops_background_work():
    source = frontend_source()

    assert "if(response.status===401)handleSessionExpired();" in source
    assert "clearBackgroundWork();" in source
    assert "renderLoginScreen('Сессия завершена. Войдите снова.');" in source
    assert "session_expires_at*1000-Date.now()" in source
    assert "scheduleSessionExpiry();" in source
    assert "SESSION_TTL" not in source  # TTL is enforced by backend, not refreshed by JS.


def test_tabs_and_data_loading_are_permission_scoped():
    source = frontend_source()

    assert "function availablePiTabs()" in source
    assert "return PI_TABS.filter(tab=>allowed.has(tab.id)&&canReadTab(tab.id));" in source
    assert "if(hasPermission('backlog:read'))" in source
    assert "if(hasPermission('pi_data:read'))await loadPiDataView(id);" in source
    assert "if(hasPermission('team_boards:read'))" in source
    assert "if(required&&!hasPermission(required))" in source


def test_every_quarter_is_selectable_and_missing_cycle_is_created_via_navigation():
    source = frontend_source()

    assert "async function ensureNavigationCycle(year,quarter)" in source
    assert "await authRequest('/app/pi-cycles',{method:'POST',body:{year,quarter}})" in source
    assert "await ensureNavigationCycle(year,q);" in source
    assert "PI-цикл ещё не создан" not in source
    assert "<small>доступен</small>" not in source


def test_read_only_mode_blocks_commands_dragging_and_background_autosave():
    source = frontend_source()

    assert "function applyAccessControls(" in source
    assert "el.draggable=false" in source
    assert "if(action){event.preventDefault();event.stopImmediatePropagation();}" in source
    assert "canWriteTab(state.ui.tab)" in source
    assert "hasPermission('team_boards:write')" in source
    assert "function canApproveTasks()" in source
    assert "if(id&&state.cycles[id])await persistTeamBoardsCycle(id);" in source
    assert "if(id&&state.cycles[id])await persistCapacityCycle(id);" in source


def test_budget_prototype_remains_bundled_but_landing_entry_is_disabled():
    source = frontend_source()

    assert 'src="js/budget.js' in source
    assert "Будет доступно позже" in source
    assert 'id="openBudget"' not in source
    assert "if(state.ui.mode==='budget')state.ui.mode=null;" in source
