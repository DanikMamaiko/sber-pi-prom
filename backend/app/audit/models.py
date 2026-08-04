from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.base import AuditBase


class AuditEventRecord(AuditBase):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_username_occurred_at", "username", "occurred_at"),
        Index("ix_audit_events_action_occurred_at", "action", "occurred_at"),
        Index("ix_audit_events_object", "object_type", "object_id"),
        Index("ix_audit_events_result_occurred_at", "result", "occurred_at"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_service: Mapped[str] = mapped_column(String(200), nullable=False)
    source_component: Mapped[str] = mapped_column(String(100), nullable=False)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    username: Mapped[str | None] = mapped_column(String(200))
    auth_provider: Mapped[str | None] = mapped_column(String(100))
    source_ip: Mapped[str | None] = mapped_column(String(64))
    host_ip: Mapped[str | None] = mapped_column(String(64))
    host_name: Mapped[str] = mapped_column(String(255), nullable=False)
    operation_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operation_finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(200))
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64))
    http_method: Mapped[str] = mapped_column(String(10), nullable=False)
    http_route: Mapped[str] = mapped_column(String(500), nullable=False)
    http_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
