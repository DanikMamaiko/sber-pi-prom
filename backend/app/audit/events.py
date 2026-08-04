from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
import uuid


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: uuid.UUID
    occurred_at: datetime
    source_service: str
    source_component: str
    environment: str
    username: str | None
    auth_provider: str | None
    source_ip: str | None
    host_ip: str | None
    host_name: str
    operation_started_at: datetime
    operation_finished_at: datetime
    duration_ms: int
    action: str
    object_type: str
    object_id: str | None
    result: str
    description: str
    request_id: uuid.UUID
    session_id: str | None
    http_method: str
    http_route: str
    http_path: str
    http_status: int
    error_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_log_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "event_id",
            "request_id",
            "occurred_at",
            "operation_started_at",
            "operation_finished_at",
        ):
            value[key] = str(value[key])
        return value
