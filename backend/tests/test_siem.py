import json
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from auth_fixtures import INVALID_TEST_PASSWORD, TEST_PASSWORDS
from app.audit.middleware import logger
from app.audit.siem import JsonFileAuditSink, UdpSyslogAuditSink, siem_payload
from app.core.config import Settings
from app.main import app


class RecordingSink:
    def __init__(self):
        self.events = []

    async def write(self, event):
        self.events.append(event)


class FailingSink:
    async def write(self, event):
        raise OSError("test destination unavailable")


@pytest.mark.parametrize(
    "password,status,event_type,outcome",
    [(TEST_PASSWORDS["editor"], 200, "login_success", "success"),
     (INVALID_TEST_PASSWORD, 401, "login_failure", "failure")],
)
def test_login_json_matches_colleague_format_without_secrets(tmp_path, password, status, event_type, outcome):
    path = tmp_path / "audit.jsonl"
    app.state.siem_audit_sink = JsonFileAuditSink(str(path))
    database = RecordingSink()
    app.state.audit_sink = database
    response = TestClient(app).post(
        "/api/auth/login?token=private-query-value",
        json={"username": "editor", "password": password},
        headers={"user-agent": "test-browser"},
    )
    assert response.status_code == status
    content = path.read_text(encoding="utf-8")
    assert len(content.splitlines()) == 1
    payload = json.loads(content)
    assert payload["service"] == "SberPI API"
    assert payload["event_category"] == "authentication"
    assert payload["event_type"] == event_type
    assert payload["outcome"] == outcome
    assert payload["username"] == "editor"
    assert payload["method"] == "POST"
    assert payload["user_agent"] == "test-browser"
    assert payload["timestamp"].endswith("Z")
    assert payload["event_id"] == str(database.events[0].event_id)
    assert payload["request_id"] == response.headers["x-request-id"]
    for secret in (password, "private-query-value", "session_id", "cookie", "password"):
        assert secret not in content


def test_database_failure_still_exports_siem_event(tmp_path):
    path = tmp_path / "audit.jsonl"
    app.state.siem_audit_sink = JsonFileAuditSink(str(path))
    app.state.audit_sink = FailingSink()
    response = TestClient(app).post(
        "/api/auth/login", json={"username": "editor", "password": TEST_PASSWORDS["editor"]},
    )
    assert response.status_code == 200
    assert json.loads(path.read_text(encoding="utf-8"))["event_type"] == "login_success"


def test_disk_failure_preserves_database_and_response():
    database = RecordingSink()
    app.state.audit_sink = database
    app.state.siem_audit_sink = FailingSink()
    with patch.object(logger, "warning") as warning:
        response = TestClient(app).post(
            "/api/auth/login", json={"username": "editor", "password": TEST_PASSWORDS["editor"]},
        )
    assert response.status_code == 200
    assert len(database.events) == 1
    assert warning.call_args.args[0] == "siem_audit_fallback %s"
    assert json.loads(warning.call_args.args[1])["event_id"] == str(database.events[0].event_id)


def test_health_probe_does_not_reach_siem():
    sink = RecordingSink()
    app.state.siem_audit_sink = sink
    assert TestClient(app).get("/api/health").status_code == 200
    assert sink.events == []


def test_logout_and_permission_denial_event_types():
    sink = RecordingSink()
    app.state.siem_audit_sink = sink
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"username": "pm", "password": TEST_PASSWORDS["pm"]}).status_code == 200
        assert client.get("/api/pi-cycles").status_code == 403
        assert client.post("/api/auth/logout").status_code == 204
    denied = siem_payload(sink.events[1])
    assert denied["event_category"] == "authorization"
    assert denied["event_type"] == "access_denied"
    assert siem_payload(sink.events[2])["event_type"] == "logout_success"


@pytest.mark.asyncio
async def test_rotation_unicode_and_newline_injection(tmp_path):
    from dataclasses import replace

    recording = RecordingSink()
    app.state.siem_audit_sink = recording
    TestClient(app).post("/api/auth/login", json={"username": "editor", "password": TEST_PASSWORDS["editor"]})
    event = replace(recording.events[0], username="Тест\r\nforged event", details={"user_agent": "X\nY" * 1000, "token": "not-exported"})
    path = tmp_path / "audit.jsonl"
    sink = JsonFileAuditSink(str(path))
    await sink.write(event)
    rotated = path.with_suffix(".1")
    path.rename(rotated)
    await sink.write(event)
    for file in (rotated, path):
        raw = file.read_bytes()
        assert raw.count(b"\n") == 1
        payload = json.loads(raw)
        assert payload["username"] == event.username
        assert len(payload["user_agent"]) == 512
        assert b"not-exported" not in raw


@pytest.mark.asyncio
async def test_concurrent_appends_are_complete_lines(tmp_path):
    import asyncio
    from dataclasses import replace
    import uuid

    recording = RecordingSink()
    app.state.siem_audit_sink = recording
    TestClient(app).post("/api/auth/login", json={"username": "editor", "password": TEST_PASSWORDS["editor"]})
    events = [replace(recording.events[0], event_id=uuid.uuid4()) for _ in range(50)]
    path = tmp_path / "audit.jsonl"
    sink = JsonFileAuditSink(str(path))
    await asyncio.gather(*(sink.write(event) for event in events))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 50
    assert {json.loads(line)["event_id"] for line in lines} == {str(event.event_id) for event in events}


def test_missing_log_directory_fails_at_startup(tmp_path):
    with pytest.raises(FileNotFoundError):
        JsonFileAuditSink(str(tmp_path / "missing" / "audit.jsonl"))


def test_siem_requires_audit_enabled_and_absolute_path(tmp_path):
    with pytest.raises(ValidationError, match="AUDIT_ENABLED"):
        Settings(audit_enabled=False, siem_audit_log_path=str(tmp_path / "audit.jsonl"), _env_file=None)
    with pytest.raises(ValidationError, match="absolute path"):
        Settings(siem_audit_log_path="relative.jsonl", _env_file=None)
    assert Settings(siem_audit_log_path="", _env_file=None).siem_audit_log_path == ""


def test_direct_udp_sends_login_events_from_api_without_file_volume():
    import socket

    database = RecordingSink()
    app.state.audit_sink = database
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as collector:
        collector.bind(("127.0.0.1", 0))
        collector.settimeout(3)
        app.state.siem_audit_sink = UdpSyslogAuditSink("127.0.0.1", collector.getsockname()[1], "sberpi-sigma")
        with TestClient(app) as client:
            for password, expected_status, event_type in (
                (INVALID_TEST_PASSWORD, 401, "login_failure"),
                (TEST_PASSWORDS["editor"], 200, "login_success"),
            ):
                response = client.post("/api/auth/login?token=private-query", json={"username": "editor", "password": password})
                assert response.status_code == expected_status
                wire, _ = collector.recvfrom(65535)
                header, body = wire.decode("utf-8").split(" - - - ", 1)
                assert header.startswith("<182>1 ")
                assert header.endswith(" sberpi-sigma sberpi.audit")
                assert b"\0" not in wire and b"\n" not in wire
                payload = json.loads(body)
                assert payload["event_type"] == event_type
                assert payload["event_id"] == str(database.events[-1].event_id)
                assert payload["request_id"] == response.headers["x-request-id"]
                assert password not in body and "private-query" not in body


def test_udp_still_sends_when_audit_database_is_unavailable():
    import socket

    app.state.audit_sink = FailingSink()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as collector:
        collector.bind(("127.0.0.1", 0))
        collector.settimeout(3)
        app.state.siem_audit_sink = UdpSyslogAuditSink("127.0.0.1", collector.getsockname()[1], "sberpi-sigma")
        response = TestClient(app).post("/api/auth/login", json={"username": "editor", "password": TEST_PASSWORDS["editor"]})
        assert response.status_code == 200
        wire, _ = collector.recvfrom(65535)
        assert json.loads(wire.decode().split(" - - - ", 1)[1])["event_type"] == "login_success"


@pytest.mark.parametrize("override", [
    {"siem_syslog_target": ""},
    {"siem_syslog_target": "<COLLECTOR_IP>"},
    {"siem_syslog_target": "256.0.0.1"},
    {"siem_syslog_target": "https://192.0.2.10"},
    {"siem_syslog_protocol": "tcp"},
    {"siem_syslog_port": 0},
    {"siem_syslog_port": 65536},
    {"siem_syslog_hostname": "injected\nheader"},
    {"audit_enabled": False},
])
def test_direct_udp_rejects_invalid_configuration(override):
    values = {"siem_syslog_enabled": True, "siem_syslog_target": "192.0.2.10", **override}
    with pytest.raises(ValidationError):
        Settings(**values, _env_file=None)


def test_direct_udp_and_file_export_are_mutually_exclusive(tmp_path):
    with pytest.raises(ValidationError, match="not both"):
        Settings(siem_syslog_enabled=True, siem_syslog_target="192.0.2.10", siem_audit_log_path=str(tmp_path / "audit.jsonl"), _env_file=None)


def test_direct_udp_configuration_is_disabled_by_default_and_accepts_ipv6():
    assert Settings(_env_file=None).siem_syslog_enabled is False
    settings = Settings(siem_syslog_enabled=True, siem_syslog_target="2001:db8::1", _env_file=None)
    assert settings.siem_syslog_port == 514
    assert settings.siem_syslog_target == "2001:db8::1"


def test_direct_udp_works_with_production_uvloop():
    import socket

    uvloop = pytest.importorskip("uvloop")
    recording = RecordingSink()
    app.state.siem_audit_sink = recording
    TestClient(app).post("/api/auth/login", json={"username": "editor", "password": TEST_PASSWORDS["editor"]})
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as collector:
        collector.bind(("127.0.0.1", 0))
        collector.settimeout(3)
        sink = UdpSyslogAuditSink("127.0.0.1", collector.getsockname()[1], "sberpi-sigma")
        uvloop.run(sink.write(recording.events[0]))
        wire, _ = collector.recvfrom(65535)
        assert json.loads(wire.decode().split(" - - - ", 1)[1])["event_id"] == str(recording.events[0].event_id)
