"""Configure the test process before application modules are imported."""
import os
import pytest

from auth_fixtures import TEST_AUTH_USERS, TEST_SESSION_SECRET

# Unit tests never use the developer's .env or credentials. Integration tests
# opt in with a dedicated TEST_DATABASE_URL and check its name before migration.
os.environ.update(
    APP_ENV="test",
    DATABASE_URL=os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://localhost:5433/sberpi_test"
    ),
    AUTH_PROVIDER="local",
    AUTH_TEST_USERS=TEST_AUTH_USERS,
    SESSION_SECRET=TEST_SESSION_SECRET,
    SESSION_TTL_MINUTES="60",
    SESSION_COOKIE_SECURE="false",
    AUDIT_ENABLED="true",
    AUDIT_DATABASE_URL="",
    SIEM_AUDIT_LOG_PATH="",
    SIEM_SYSLOG_ENABLED="false",
    SIEM_SYSLOG_TARGET="",
    SIEM_SYSLOG_PORT="514",
    SIEM_SYSLOG_PROTOCOL="udp",
    SIEM_SYSLOG_HOSTNAME="sberpi-sigma",
    JIRA_ENABLED="false",
)
os.environ.pop("SBERPI_SECRETS_DIR", None)


@pytest.fixture(autouse=True)
def isolate_audit_sink():
    from app.main import app
    from app.audit.sink import DisabledAuditSink

    previous = app.state.audit_sink
    previous_siem = app.state.siem_audit_sink
    app.state.audit_sink = DisabledAuditSink()
    app.state.siem_audit_sink = DisabledAuditSink()
    yield
    app.state.audit_sink = previous
    app.state.siem_audit_sink = previous_siem
