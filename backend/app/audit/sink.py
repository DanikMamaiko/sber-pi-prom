import time
from typing import Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.audit.events import AuditEvent
from app.audit.models import AuditEventRecord


class AuditSink(Protocol):
    async def write(self, event: AuditEvent) -> None: ...


class DisabledAuditSink:
    async def write(self, event: AuditEvent) -> None:
        return None


class AuditSinkUnavailable(RuntimeError):
    pass


class DatabaseAuditSink:
    """Append-only application writer for the dedicated audit database.

    A short circuit breaker prevents an unavailable audit database from adding a
    connection timeout to every API request. The middleware emits a structured
    fallback log whenever this sink cannot persist an event.
    """

    def __init__(
        self,
        database_url: str,
        *,
        connect_timeout_seconds: int = 3,
        retry_seconds: int = 30,
    ):
        # NullPool also keeps short-lived workers and test event loops from sharing
        # an asyncpg connection created by a different event loop.
        self.engine = create_async_engine(
            database_url,
            echo=False,
            poolclass=NullPool,
            connect_args={"timeout": connect_timeout_seconds},
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.retry_seconds = retry_seconds
        self._retry_after = 0.0

    async def write(self, event: AuditEvent) -> None:
        now = time.monotonic()
        if now < self._retry_after:
            raise AuditSinkUnavailable("audit database circuit breaker is open")
        try:
            async with self.session_factory() as session:
                session.add(
                    AuditEventRecord(
                        event_id=event.event_id,
                        occurred_at=event.occurred_at,
                        source_service=event.source_service,
                        source_component=event.source_component,
                        environment=event.environment,
                        username=event.username,
                        auth_provider=event.auth_provider,
                        source_ip=event.source_ip,
                        host_ip=event.host_ip,
                        host_name=event.host_name,
                        operation_started_at=event.operation_started_at,
                        operation_finished_at=event.operation_finished_at,
                        duration_ms=event.duration_ms,
                        action=event.action,
                        object_type=event.object_type,
                        object_id=event.object_id,
                        result=event.result,
                        description=event.description,
                        request_id=event.request_id,
                        session_id=event.session_id,
                        http_method=event.http_method,
                        http_route=event.http_route,
                        http_path=event.http_path,
                        http_status=event.http_status,
                        error_code=event.error_code,
                        details=event.details,
                    )
                )
                await session.commit()
        except Exception:
            self._retry_after = time.monotonic() + self.retry_seconds
            raise
