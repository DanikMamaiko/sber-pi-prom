from auth_fixtures import TEST_SERVICE_PASSWORD

from app.core.config import Settings
from pydantic import ValidationError
import pytest


def test_audit_uses_main_database_when_no_override_is_set():
    settings = Settings(
        database_url="postgresql+asyncpg://app@db:5432/sberpi",
        audit_database_url="",
        _env_file=None,
    )

    assert settings.effective_audit_database_url == settings.database_url


def test_legacy_separate_audit_database_remains_supported():
    settings = Settings(
        database_url="postgresql+asyncpg://app@db:5432/sberpi",
        audit_database_url="postgresql+asyncpg://audit@db:5432/audit",
        _env_file=None,
    )

    assert settings.effective_audit_database_url == settings.audit_database_url


def test_jira_requires_explicit_enablement_and_credentials():
    disabled = Settings(
        jira_enabled=False,
        jira_username="usertest",
        jira_password=TEST_SERVICE_PASSWORD,
        _env_file=None,
    )
    enabled = Settings(
        jira_enabled=True,
        jira_username="usertest",
        jira_password=TEST_SERVICE_PASSWORD,
        _env_file=None,
    )

    assert disabled.jira_is_configured is False
    assert enabled.jira_is_configured is True


def test_ift_ldap_defaults_use_plain_port_and_all_four_direct_role_groups():
    settings = Settings(_env_file=None)

    assert settings.ldap_url == "ldap://sigma-belpsb.by:389"
    assert settings.ldap_use_tls is False
    assert settings.ldap_user_search_base == "DC=sigma-belpsb,DC=by"
    assert settings.ldap_user_filter == "(sAMAccountName={username})"
    assert settings.ad_group_admin.startswith("CN=SberPI-Admins,")
    assert settings.ad_group_planning_editor.startswith("CN=SberPI-PlanningEditors,")
    assert settings.ad_group_business_viewer.startswith("CN=SberPI-BusinessViewers,")
    assert settings.ad_group_viewer.startswith("CN=SberPI-Viewers,")


@pytest.mark.parametrize("variable", ["DATABASE_URL", "SESSION_SECRET", "AUTH_TEST_USERS"])
def test_runtime_has_no_fallback_credentials(monkeypatch, variable):
    monkeypatch.delenv(variable, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("users", ["", " ", "broken", "user::viewer", "admin:CHANGE_ME:admin"])
def test_local_auth_requires_explicit_valid_users(users):
    with pytest.raises(ValidationError):
        Settings(auth_test_users=users, _env_file=None)


@pytest.mark.parametrize("field", ["database_url", "session_secret"])
@pytest.mark.parametrize("value", ["", " ", "CHANGE_ME", "<TEST_PASSWORD>"])
def test_required_settings_reject_empty_values_and_documentation_placeholders(field, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_production_requires_a_long_session_key():
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(app_env="production", session_secret=TEST_SERVICE_PASSWORD[:16], _env_file=None)


def test_ldap_does_not_require_or_create_local_test_users(monkeypatch):
    monkeypatch.delenv("AUTH_TEST_USERS", raising=False)
    settings = Settings(auth_provider="ldap", app_env="production", _env_file=None)
    assert settings.auth_test_users == ""


def test_mounted_secrets_override_environment_and_support_both_databases(tmp_path):
    from auth_fixtures import TEST_SESSION_SECRET, TEST_PASSWORDS

    values = {
        "DATABASE_URL": "postgresql+asyncpg://app@db:5432/sberpi",
        "AUDIT_DATABASE_URL": "postgresql+asyncpg://audit@db:5432/audit",
        "SESSION_SECRET": TEST_SESSION_SECRET,
        "LDAP_BIND_PASSWORD": TEST_PASSWORDS["user"],
        "JIRA_PASSWORD": TEST_PASSWORDS["editor"],
    }
    for name, value in values.items():
        (tmp_path / name).write_text(value, encoding="utf-8")
    settings = Settings(_env_file=None, _secrets_dir=tmp_path)
    for name, value in values.items():
        assert getattr(settings, name.lower()) == value
        assert value not in repr(settings)
    assert settings.effective_audit_database_url == values["AUDIT_DATABASE_URL"]


def test_get_settings_uses_secret_mount_for_application_and_alembic(monkeypatch, tmp_path):
    from app.core.config import get_settings

    monkeypatch.setenv("SBERPI_SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL")
    (tmp_path / "DATABASE_URL").write_text("postgresql+asyncpg://app@db:5432/sberpi", encoding="utf-8")
    get_settings.cache_clear()
    try:
        assert get_settings().database_url == "postgresql+asyncpg://app@db:5432/sberpi"
    finally:
        get_settings.cache_clear()


def test_missing_secret_mount_fails_instead_of_silently_falling_back(monkeypatch, tmp_path):
    from app.core.config import get_settings

    monkeypatch.setenv("SBERPI_SECRETS_DIR", str(tmp_path / "missing"))
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="existing mounted secret directory"):
            get_settings()
    finally:
        get_settings.cache_clear()
