"""Security audit JSON: direct UDP syslog or an optional rsyslog input file."""

from datetime import timezone
import ipaddress
import json
import os
from pathlib import Path
import socket
from threading import Lock

from starlette.concurrency import run_in_threadpool

from app.audit.events import AuditEvent


def siem_payload(event: AuditEvent) -> dict:
    """Explicit allowlist: never export cookies, bodies, query strings or tokens."""
    operation = event.action.removeprefix("authentication.")
    if event.action.startswith("authentication."):
        category = "authentication"
        event_type = f"{operation}_{event.result}"
    elif event.http_status == 403:
        category = "authorization"
        event_type = "access_denied"
    else:
        category = "application"
        event_type = f"{event.action.replace('.', '_')}_{event.result}"

    def limited(value: str | None, size: int = 256) -> str | None:
        return value[:size] if value is not None else None

    return {
        "service": "SberPI API",
        "logger": "sberpi.audit",
        "event_category": category,
        "event_type": event_type,
        "outcome": event.result,
        "source_ip": limited(event.source_ip),
        "username": limited(event.username),
        "method": event.http_method,
        "path": limited(event.http_route, 512),
        "status_code": event.http_status,
        "user_agent": limited(event.details.get("user_agent"), 512),
        "description": limited(event.description, 512),
        "timestamp": event.occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event_id": str(event.event_id),
        "request_id": str(event.request_id),
        "source_service": limited(event.source_service),
        "environment": limited(event.environment),
        "host_name": limited(event.host_name),
        "host_ip": limited(event.host_ip),
        "action": event.action,
        "object_type": event.object_type,
        "object_id": limited(event.object_id),
        "error_code": event.error_code,
        "duration_ms": event.duration_ms,
    }


def siem_json(event: AuditEvent) -> str:
    # JSON escapes embedded CR/LF, preventing forged extra syslog events.
    return json.dumps(siem_payload(event), ensure_ascii=False, separators=(",", ":"))


class UdpSyslogAuditSink:
    """Best-effort RFC 5424 UDP. A successful send is not a collector receipt.

    The collector IP is validated at startup, so there is no DNS/network probe.
    Each nonblocking socket lives for one send and cannot leak across workers or
    event loops. Local errors propagate to the audit middleware's fallback; the
    normal database audit is still attempted. UDP has no retry or acknowledgement.
    """

    def __init__(self, target: str, port: int, hostname: str):
        address = ipaddress.ip_address(target)
        self.family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        self.destination = (str(address), port)
        self.hostname = hostname

    async def write(self, event: AuditEvent) -> None:
        timestamp = event.occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        # local6.info = 22 * 8 + 6 = 182; datagram boundary supplies framing.
        message = f"<182>1 {timestamp} {self.hostname} sberpi.audit - - - {siem_json(event)}"
        data = message.encode("utf-8", errors="backslashreplace")
        if len(data) > 65507:
            raise ValueError("SIEM event exceeds the UDP datagram limit")
        with socket.socket(self.family, socket.SOCK_DGRAM) as sender:
            sender.setblocking(False)
            # One nonblocking syscall; numeric IP means no DNS lookup. Unlike
            # loop.sock_sendto, this also works with Uvicorn's uvloop. A full
            # local send buffer raises BlockingIOError and uses the fallback.
            sent = sender.sendto(data, self.destination)
        if sent != len(data):
            raise OSError("Incomplete SIEM UDP send")


class JsonFileAuditSink:
    """Append on a worker thread; reopen each time to support rename-based rotation.

    The host directory must be provisioned explicitly. Fail startup on an invalid
    destination, and propagate later disk errors to the middleware's fallback.
    There are no sockets or collector timeouts on the HTTP request path.
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = Lock()
        with self._open():
            pass

    def _open(self):
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)
        return os.fdopen(fd, "ab")

    def _append(self, data: bytes) -> None:
        with self._lock, self._open() as stream:
            stream.write(data)

    async def write(self, event: AuditEvent) -> None:
        data = (siem_json(event) + "\n").encode("utf-8", errors="backslashreplace")
        await run_in_threadpool(self._append, data)
