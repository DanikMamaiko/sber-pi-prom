import pytest
from ldap3 import MOCK_SYNC, Connection, Server

from app.auth.providers import AuthProviderUnavailable, LdapAuthProvider


@pytest.mark.asyncio
@pytest.mark.parametrize("base_exists", [True, False])
async def test_empty_user_search_is_distinguished_from_invalid_base(monkeypatch, base_exists):
    server = Server("ldap.example.test")
    bind_dn = "CN=Service,DC=example,DC=test"
    search_base = "OU=Users,DC=example,DC=test"
    connection = Connection(
        server, user=bind_dn, password="test-only", client_strategy=MOCK_SYNC,
        check_names=False,
    )
    connection.strategy.add_entry(bind_dn, {"userPassword": "test-only", "objectClass": "person"})
    if base_exists:
        connection.strategy.add_entry(search_base, {"objectClass": "organizationalUnit"})
    provider = LdapAuthProvider(
        url="ldap://ldap.example.test:389",
        user_search_base=search_base,
        user_filter="(cn={username})",
        bind_dn=bind_dn,
        bind_password="test-only",
        role_groups={"viewer": "CN=Viewers,DC=example,DC=test"},
    )
    monkeypatch.setattr(provider, "_connection", lambda *args: connection)

    if base_exists:
        assert await provider.authenticate("missing-user", "any-password") is None
    else:
        with pytest.raises(AuthProviderUnavailable, match="LDAP не выполнил поиск пользователя"):
            await provider.authenticate("missing-user", "any-password")
