import socket
from struct import pack
from unittest.mock import MagicMock

import pytest
from ldap3.strategy import base

from app.auth.providers import LdapAuthProvider


@pytest.mark.parametrize("timeout,expected_seconds", [(5.0, 5), (5.1, 6)])
@pytest.mark.parametrize("address_count", [1, 2])
def test_ldap_socket_opens_with_linux_receive_timeout(
    monkeypatch, timeout, expected_seconds, address_count
):
    """Exercise ldap3's real Linux timeout encoding without contacting AD."""
    provider = LdapAuthProvider(
        url="ldap://127.0.0.1:389",
        user_search_base="DC=example,DC=test",
        user_filter="(cn={username})",
        bind_dn="service@example.test",
        bind_password="test-only-password",
        role_groups={"viewer": "CN=Viewers,DC=example,DC=test"},
        connect_timeout_seconds=timeout,
    )
    connection = provider._connection("service@example.test", "test-only-password")
    addresses = [
        [socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (f"127.0.0.{i + 1}", 389), None, None]
        for i in range(address_count)
    ]
    monkeypatch.setattr(provider._server, "candidate_addresses", lambda: addresses)
    monkeypatch.setattr(provider._server, "update_availability", lambda *args: None)
    fake_socket = MagicMock()
    fake_socket.family = socket.AF_INET
    monkeypatch.setattr(base, "system", lambda: "Linux")
    monkeypatch.setattr(base.socket, "socket", lambda *args, **kwargs: fake_socket)

    try:
        connection.open(read_server_info=False)
        assert connection.closed is False
        fake_socket.setsockopt.assert_called_with(
            socket.SOL_SOCKET, socket.SO_RCVTIMEO, pack("LL", expected_seconds, 0)
        )
    finally:
        connection.unbind()
