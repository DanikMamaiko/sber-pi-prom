import ssl
from unittest.mock import MagicMock

import pytest
from ldap3.core import tls as ldap_tls
from ldap3.core.exceptions import LDAPCertificateError

from app.auth.providers import LdapAuthProvider
from app.auth import service
from app.core.config import Settings
from auth_fixtures import TEST_SERVICE_PASSWORD


def make_provider(**overrides):
    options = dict(
        url="ldaps://dc.example.test:636",
        user_search_base="DC=example,DC=test",
        user_filter="(cn={username})",
        bind_dn="service@example.test",
        bind_password=TEST_SERVICE_PASSWORD,
        role_groups={"viewer": "CN=Viewers,DC=example,DC=test"},
    )
    return LdapAuthProvider(**(options | overrides))


@pytest.mark.parametrize("use_tls", [False, True])
def test_ldaps_url_always_requires_certificate_validation(use_tls):
    server = make_provider(use_tls=use_tls)._server
    assert server.ssl is True
    assert server.port == 636
    assert server.tls.validate == ssl.CERT_REQUIRED
    assert server.tls.ca_certs_file is None  # system trust store


def test_tls_flag_cannot_be_silently_overridden_by_plain_url():
    with pytest.raises(ValueError, match="StartTLS"):
        make_provider(url="ldap://dc.example.test:389", use_tls=True)


def test_ca_bundle_cannot_be_silently_ignored_on_plain_ldap():
    with pytest.raises(ValueError, match="LDAPS"):
        make_provider(url="ldap://dc.example.test:389", ca_bundle="ca.pem")


@pytest.mark.parametrize("content", [None, b"not a certificate", b"\x30\x82\x00\x01"])
def test_missing_or_invalid_ca_file_is_rejected(tmp_path, content):
    bundle = tmp_path / "ca.pem"
    if content is not None:
        bundle.write_bytes(content)
    with pytest.raises(ValueError, match="LDAP_CA_BUNDLE"):
        make_provider(ca_bundle=str(bundle))


def test_ldap_ca_environment_setting_reaches_provider(tmp_path, monkeypatch):
    # Use an actual trusted PEM certificate without adding a test key or dependency.
    root = ssl.create_default_context().get_ca_certs(binary_form=True)[0]
    bundle = tmp_path / "ca.pem"
    bundle.write_text(ssl.DER_cert_to_PEM_cert(root), encoding="ascii")
    monkeypatch.setenv("LDAP_CA_BUNDLE", str(bundle))
    settings = Settings(
        auth_provider="ldap", ldap_url="ldaps://dc.example.test:636",
        ldap_bind_dn="service@example.test", ldap_bind_password=TEST_SERVICE_PASSWORD,
        _env_file=None,
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    service.get_auth_service.cache_clear()
    try:
        server = service.get_auth_service().provider._server
        assert server.tls.ca_certs_file == str(bundle)
        assert server.tls.validate == ssl.CERT_REQUIRED
    finally:
        service.get_auth_service.cache_clear()


@pytest.mark.parametrize("dns_name,accepted", [("dc.example.test", True), ("other.example.test", False)])
def test_ldap3_checks_hostname_after_handshake(monkeypatch, dns_name, accepted):
    provider = make_provider()
    connection = provider._connection("service@example.test", TEST_SERVICE_PASSWORD)
    context = MagicMock()
    context.wrap_socket.return_value.getpeercert.return_value = {
        "subjectAltName": (("DNS", dns_name),),
    }
    monkeypatch.setattr(ldap_tls, "create_default_context", lambda **kwargs: context)
    if accepted:
        provider._server.tls.wrap_socket(connection, do_handshake=True)
    else:
        with pytest.raises(LDAPCertificateError):
            provider._server.tls.wrap_socket(connection, do_handshake=True)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.wrap_socket.call_args.kwargs["do_handshake_on_connect"] is True


def test_bind_credentials_are_not_forwarded_to_referrals():
    connection = make_provider()._connection("service@example.test", TEST_SERVICE_PASSWORD)
    assert connection.auto_referrals is False
