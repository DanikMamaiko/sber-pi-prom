from app.core.config import Settings


def test_audit_uses_main_database_when_no_override_is_set():
    settings = Settings(
        database_url="postgresql+asyncpg://app:secret@db:5432/sberpi",
        audit_database_url="",
        _env_file=None,
    )

    assert settings.effective_audit_database_url == settings.database_url


def test_legacy_separate_audit_database_remains_supported():
    settings = Settings(
        database_url="postgresql+asyncpg://app:secret@db:5432/sberpi",
        audit_database_url="postgresql+asyncpg://audit:secret@db:5432/audit",
        _env_file=None,
    )

    assert settings.effective_audit_database_url == settings.audit_database_url


def test_jira_requires_explicit_enablement_and_credentials():
    disabled = Settings(
        jira_enabled=False,
        jira_username="usertest",
        jira_password="secret",
        _env_file=None,
    )
    enabled = Settings(
        jira_enabled=True,
        jira_username="usertest",
        jira_password="secret",
        _env_file=None,
    )

    assert disabled.jira_is_configured is False
    assert enabled.jira_is_configured is True
