import pytest

from app.auth.permissions import ALL_PERMISSIONS, Permission, ROLE_PERMISSIONS, permissions_for_roles
from app.auth import providers
from app.auth.providers import AuthProviderUnavailable, LdapAuthProvider, LocalAuthProvider


EXPECTED = {
    "admin": ALL_PERMISSIONS,
    "planning_editor": {
        Permission.APP_NAVIGATE,
        Permission.PI_CYCLE_SELECT,
        Permission.BACKLOG_READ,
        Permission.BACKLOG_WRITE,
        Permission.PRE_PI_READ,
        Permission.PRE_PI_WRITE,
        Permission.GOALS_READ,
        Permission.TEAM_BOARDS_READ,
        Permission.TEAM_BOARDS_WRITE,
        Permission.TASKS_APPROVE,
        Permission.PROGRAM_BOARD_READ,
        Permission.PROGRAM_BOARD_WRITE,
        Permission.RISKS_READ,
        Permission.RISKS_WRITE,
    },
    "business_viewer": {
        Permission.APP_NAVIGATE,
        Permission.PI_CYCLE_SELECT,
        Permission.BACKLOG_READ,
        Permission.PRE_PI_READ,
        Permission.PRE_PI_WRITE,
        Permission.GOALS_READ,
        Permission.TEAM_BOARDS_READ,
        Permission.PROGRAM_BOARD_READ,
        Permission.RISKS_READ,
    },
    "viewer": {
        Permission.APP_NAVIGATE,
        Permission.PI_CYCLE_SELECT,
        Permission.BACKLOG_READ,
        Permission.PRE_PI_READ,
        Permission.GOALS_READ,
        Permission.TEAM_BOARDS_READ,
        Permission.PROGRAM_BOARD_READ,
        Permission.RISKS_READ,
    },
}


@pytest.mark.parametrize("role", EXPECTED)
def test_role_permission_matrix(role):
    assert ROLE_PERMISSIONS[role] == frozenset(EXPECTED[role])


def test_permissions_are_unioned_for_multiple_provider_roles():
    permissions = permissions_for_roles(("business_viewer", "planning_editor"))
    assert permissions == ROLE_PERMISSIONS["business_viewer"] | ROLE_PERMISSIONS["planning_editor"]


@pytest.mark.asyncio
async def test_local_provider_authenticates_users_and_rejects_bad_password():
    provider = LocalAuthProvider(
        "admin:secret:admin,po_itl:pass:planning_editor,user:pass:viewer"
    )

    identity = await provider.authenticate("admin", "secret")

    assert identity is not None
    assert identity.username == "admin"
    assert identity.roles == ("admin",)
    po_itl = await provider.authenticate("po_itl", "pass")
    assert po_itl is not None
    assert po_itl.roles == ("planning_editor",)
    assert await provider.authenticate("admin", "wrong") is None
    assert await provider.authenticate("missing", "secret") is None


@pytest.mark.parametrize(
    "raw_users",
    (
        "broken",
        "user::viewer",
        "user:pass:unknown",
        "user:one:viewer,user:two:admin",
    ),
)
def test_local_provider_rejects_invalid_configuration(raw_users):
    with pytest.raises(ValueError):
        LocalAuthProvider(raw_users)


class _FakeAttribute:
    def __init__(self, *, value=None, values=()):
        self.value = value
        self.values = list(values)


class _FakeEntry:
    entry_dn = "CN=Test User,OU=Users ALL,DC=sigma-belpsb,DC=by"

    def __init__(self, groups):
        self.sAMAccountName = _FakeAttribute(value="test.user")
        self.memberOf = _FakeAttribute(values=groups)

    def __contains__(self, attribute):
        return attribute in {"sAMAccountName", "memberOf"}


def _ldap_provider(monkeypatch, *, groups, user_password="domain-secret", service_binds=True):
    captured = {"connections": [], "search_filter": None}

    class FakeConnection:
        def __init__(self, _server, *, user, password, **_kwargs):
            self.user = user
            self.password = password
            self.entries = []
            self.result = {"result": 0}
            captured["connections"].append(self)

        def bind(self):
            if self.user == "service@belpsb.by":
                return service_binds
            if self.password == user_password:
                return True
            self.result = {"result": 49}
            return False

        def search(self, *, search_filter, **_kwargs):
            captured["search_filter"] = search_filter
            self.entries = [_FakeEntry(groups)]
            return True

        def unbind(self):
            return True

    monkeypatch.setattr(providers, "Server", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(providers, "Connection", FakeConnection)
    provider = LdapAuthProvider(
        url="ldap://sigma-belpsb.by:389",
        user_search_base="OU=Users ALL,DC=sigma-belpsb,DC=by",
        user_filter="(cn={username})",
        bind_dn="service@belpsb.by",
        bind_password="service-secret",
        use_tls=False,
        role_groups={
            "admin": "CN=SberPI-Admins,OU=SberPI,DC=sigma-belpsb,DC=by",
            "planning_editor": "CN=SberPI-PlanningEditors,OU=SberPI,DC=sigma-belpsb,DC=by",
            "business_viewer": "CN=SberPI-BusinessViewers,OU=SberPI,DC=sigma-belpsb,DC=by",
            "viewer": "CN=SberPI-Viewers,OU=SberPI,DC=sigma-belpsb,DC=by",
        },
    )
    return provider, captured


@pytest.mark.asyncio
async def test_ldap_authenticates_user_and_maps_direct_groups(monkeypatch):
    provider, _captured = _ldap_provider(
        monkeypatch,
        groups=(
            "CN=SberPI-PlanningEditors,OU=SberPI,DC=sigma-belpsb,DC=by",
            "CN=SberPI-Viewers,OU=SberPI,DC=sigma-belpsb,DC=by",
        ),
    )

    identity = await provider.authenticate("test.user", "domain-secret")

    assert identity is not None
    assert identity.username == "test.user"
    assert identity.roles == ("planning_editor", "viewer")
    assert identity.provider == "ldap"


@pytest.mark.asyncio
async def test_ldap_rejects_wrong_password_and_non_member(monkeypatch):
    provider, _captured = _ldap_provider(
        monkeypatch,
        groups=("CN=SberPI-Viewers,OU=SberPI,DC=sigma-belpsb,DC=by",),
    )
    assert await provider.authenticate("test.user", "wrong") is None

    provider, captured = _ldap_provider(
        monkeypatch,
        groups=("CN=SomeOtherGroup,OU=Groups,DC=sigma-belpsb,DC=by",),
    )
    assert await provider.authenticate("test.user", "domain-secret") is None
    assert len(captured["connections"]) == 1


@pytest.mark.asyncio
async def test_ldap_escapes_username_in_search_filter(monkeypatch):
    provider, captured = _ldap_provider(
        monkeypatch,
        groups=("CN=SberPI-Viewers,OU=SberPI,DC=sigma-belpsb,DC=by",),
    )

    await provider.authenticate("*)(cn=*)", "domain-secret")

    assert captured["search_filter"] == r"(cn=\2a\29\28cn=\2a\29)"


@pytest.mark.asyncio
async def test_ldap_provider_unavailability_never_falls_back_to_local(monkeypatch):
    provider, _captured = _ldap_provider(
        monkeypatch,
        groups=(),
        service_binds=False,
    )

    with pytest.raises(AuthProviderUnavailable):
        await provider.authenticate("admin", "admin123")
