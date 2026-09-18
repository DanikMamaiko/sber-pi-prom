"""Optional Linux checks with actual rsyslog; only loopback sockets are used."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from fastapi.testclient import TestClient
import pytest

from app.audit.siem import JsonFileAuditSink
from app.main import app
from auth_fixtures import INVALID_TEST_PASSWORD


pytestmark = pytest.mark.skipif(shutil.which("rsyslogd") is None, reason="requires Linux rsyslogd")
REPO = Path(__file__).resolve().parents[2]


def configure(tmp_path, protocol, port):
    spool = tmp_path / "spool"
    spool.mkdir()
    source = tmp_path / "audit.jsonl"
    app.state.siem_audit_sink = JsonFileAuditSink(str(source))
    template = (REPO / "deploy/rsyslog/60-sberpi-qradar.conf.example").read_text()
    template = template.replace("CHANGE_ME_COLLECTOR_IP", "127.0.0.1")
    template = template.replace("CHANGE_ME_COLLECTOR_PORT", str(port))
    template = template.replace("CHANGE_ME_TRANSPORT", protocol)
    template = template.replace("/var/log/sberpi/audit.jsonl", str(source))
    template = template.replace("/var/spool/rsyslog-sberpi", str(spool))
    config = tmp_path / "rsyslog.conf"
    config.write_text(f'global(workDirectory="{spool}" maxMessageSize="64k")\n' + template)
    subprocess.run(["rsyslogd", "-N1", "-f", str(config)], check=True, capture_output=True)
    return config, source, spool


def launch(config, stderr):
    return subprocess.Popen(
        ["rsyslogd", "-n", "-f", str(config), "-i", str(config.with_suffix(".pid"))],
        stdout=subprocess.DEVNULL, stderr=stderr,
    )


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        pytest.fail("rsyslog failed to stop gracefully")


def login_event():
    response = TestClient(app).post(
        "/api/auth/login",
        json={"username": "test.user", "password": INVALID_TEST_PASSWORD},
        headers={"user-agent": "test-browser"},
    )
    assert response.status_code == 401


def receive(listener, protocol):
    if protocol == "udp":
        return listener.recvfrom(65535)[0]
    connection, _ = listener.accept()
    with connection:
        connection.settimeout(15)
        with connection.makefile("rb") as reader:
            return reader.readline()


def check_message(wire, source):
    header, body = wire.decode("utf-8").split(" - - - ", 1)
    assert header.startswith("<182>1 ")
    assert header.endswith(" sberpi-sigma sberpi.audit")
    assert b"\0" not in wire
    payload = json.loads(body)
    assert payload == json.loads(source.read_text())
    assert payload["event_type"] == "login_failure"


@pytest.mark.parametrize("protocol", ["tcp", "udp"])
def test_real_rsyslog_forwarding(tmp_path, protocol):
    kind = socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM
    with socket.socket(socket.AF_INET, kind) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.settimeout(15)
        if protocol == "tcp":
            listener.listen()
        config, source, _ = configure(tmp_path, protocol, listener.getsockname()[1])
        with (tmp_path / "stderr.log").open("wb") as stderr:
            process = launch(config, stderr)
            try:
                login_event()
                check_message(receive(listener, protocol), source)
            finally:
                stop(process)


def test_tcp_queue_survives_rsyslog_restart_while_collector_is_down(tmp_path):
    # A bound but non-listening port deterministically refuses TCP connections.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.settimeout(15)
        config, source, spool = configure(tmp_path, "tcp", listener.getsockname()[1])
        with (tmp_path / "stderr.log").open("wb") as stderr:
            process = launch(config, stderr)
            try:
                login_event()
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if any(b"login_failure" in file.read_bytes() for file in spool.glob("sberpi-qradar.*")):
                        break
                    time.sleep(0.1)
                else:
                    pytest.fail("event was not persisted in the disk queue")
            finally:
                stop(process)
            listener.listen()
            process = launch(config, stderr)
            try:
                check_message(receive(listener, "tcp"), source)
            finally:
                stop(process)


@pytest.mark.skipif(not hasattr(os, "geteuid") or (hasattr(os, "geteuid") and os.geteuid() != 0), reason="requires root inside a test container")
def test_host_logrotate_preserves_container_uid_without_host_account(tmp_path):
    if shutil.which("logrotate") is None:
        pytest.skip("requires logrotate")
    source = tmp_path / "audit.jsonl"
    source.write_text('{"event_type":"login_success"}\n')
    os.chown(source, 10001, 10001)
    template = (REPO / "deploy/rsyslog/sberpi.logrotate").read_text()
    config = tmp_path / "logrotate.conf"
    config.write_text(template.replace("/var/log/sberpi/audit.jsonl", str(source)))
    config.chmod(0o644)
    subprocess.run(["logrotate", "-f", "-s", str(tmp_path / "rotation.state"), str(config)], check=True, capture_output=True)
    assert source.read_bytes() == b""
    assert (source.stat().st_uid, source.stat().st_gid) == (10001, 10001)
    assert source.stat().st_mode & 0o777 == 0o640
    assert json.loads(source.with_suffix(".jsonl.1").read_text())["event_type"] == "login_success"
