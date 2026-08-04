import json
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.audit.events import AuditEvent
from app.audit.middleware import _action_for, _object_type, logger as audit_logger, source_ip
from app.main import app


class MemoryAuditSink:
    def __init__(self):
        self.events: list[AuditEvent] = []

    async def write(self, event: AuditEvent) -> None:
        self.events.append(event)


class FailingAuditSink:
    async def write(self, event: AuditEvent) -> None:
        raise ConnectionError("test audit database outage")


def _with_memory_sink():
    sink = MemoryAuditSink()
    previous = app.state.audit_sink
    app.state.audit_sink = sink
    return sink, previous


def test_successful_login_and_logout_are_audited_without_secrets():
    sink, previous = _with_memory_sink()
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "editor", "password": "editor123"},
            )
            assert login.status_code == 200
            assert login.headers["x-request-id"]

            logout = client.post("/api/auth/logout")
            assert logout.status_code == 204
    finally:
        app.state.audit_sink = previous

    login_event, logout_event = sink.events
    assert login_event.action == "authentication.login"
    assert login_event.username == "editor"
    assert login_event.result == "success"
    assert login_event.http_status == 200
    assert login_event.operation_finished_at >= login_event.operation_started_at
    assert login_event.session_id
    assert "editor123" not in json.dumps(login_event.as_log_dict())

    assert logout_event.action == "authentication.logout"
    assert logout_event.username == "editor"
    assert logout_event.result == "success"
    assert logout_event.http_status == 204


def test_failed_login_records_attempted_username_and_reason():
    sink, previous = _with_memory_sink()
    try:
        response = TestClient(app).post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
    finally:
        app.state.audit_sink = previous

    assert response.status_code == 401
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.action == "authentication.login"
    assert event.username == "admin"
    assert event.result == "failure"
    assert event.error_code == "invalid_credentials"


def test_forbidden_data_access_is_audited():
    sink, previous = _with_memory_sink()
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "pm", "password": "pm123"},
            )
            assert login.status_code == 200
            response = client.get("/api/backlog-board")
    finally:
        app.state.audit_sink = previous

    assert response.status_code == 403
    event = sink.events[-1]
    assert event.action == "backlog_board.read"
    assert event.object_type == "backlog_board"
    assert event.username == "pm"
    assert event.result == "failure"
    assert event.error_code == "permission_denied"


def test_health_probe_is_not_a_user_audit_event():
    sink, previous = _with_memory_sink()
    try:
        response = TestClient(app).get("/api/health")
    finally:
        app.state.audit_sink = previous

    assert response.status_code == 200
    assert sink.events == []


def test_audit_database_outage_does_not_change_completed_operation():
    previous = app.state.audit_sink
    app.state.audit_sink = FailingAuditSink()
    try:
        with (
            patch.object(audit_logger, "error") as error_log,
            patch.object(audit_logger, "warning") as fallback_log,
        ):
            response = TestClient(app).post(
                "/api/auth/login",
                json={"username": "editor", "password": "editor123"},
            )
    finally:
        app.state.audit_sink = previous

    assert response.status_code == 200
    error_log.assert_called_once()
    fallback_log.assert_called_once()
    assert fallback_log.call_args.args[0] == "audit_fallback %s"


def test_specific_nested_resource_wins_over_pi_cycle_prefix():
    route = "/api/pi-cycles/{cycle_id}/pirs/{pir_id}"
    resource = _object_type(route)
    assert resource == "pi_event"
    assert _action_for("PATCH", route, resource) == "pi_event.update"


def test_forwarded_ip_is_used_only_for_a_trusted_proxy():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/auth/me",
        "headers": [(b"x-forwarded-for", b"203.0.113.10, 10.0.0.2")],
        "client": ("10.0.0.2", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    }
    request = Request(scope)
    assert source_ip(request, ["10.0.0.0/8"]) == "203.0.113.10"
    assert source_ip(request, ["192.168.0.0/16"]) == "10.0.0.2"
