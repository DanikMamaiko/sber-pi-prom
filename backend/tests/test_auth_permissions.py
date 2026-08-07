import pytest

from app.auth.permissions import ALL_PERMISSIONS, Permission, ROLE_PERMISSIONS, permissions_for_roles
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
    provider = LocalAuthProvider("admin:secret:admin,user:pass:viewer")

    identity = await provider.authenticate("admin", "secret")

    assert identity is not None
    assert identity.username == "admin"
    assert identity.roles == ("admin",)
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


@pytest.mark.asyncio
async def test_ldap_skeleton_never_falls_back_to_local_users():
    with pytest.raises(AuthProviderUnavailable):
        await LdapAuthProvider().authenticate("admin", "admin123")
