import asyncio
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import logging
import socket
import time
from typing import Any
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.audit.events import AuditEvent
from app.auth.session import InvalidSession, get_session_manager
from app.core.config import Settings


logger = logging.getLogger("sberpi.audit")

_RESOURCE_MARKERS = (
    ("/team-boards/initiatives/{initiative_id}/work-items", "work_item"),
    ("/team-boards/initiatives/{initiative_id}/stories", "story"),
    ("/team-boards/initiatives", "initiative"),
    ("/program-board/connections", "program_board_connection"),
    ("/risks-board/risks", "risk"),
    ("/goals-board/goals", "goal"),
    ("/capacity/members", "capacity_member"),
    ("/pre-pi/initiatives", "initiative"),
    ("/backlog-board/items", "backlog_item"),
    ("/cycle-teams", "cycle_team"),
    ("/goal-options", "goal_option"),
    ("/team-members", "team_member"),
    ("/pirs", "pi_event"),
    ("/regressions", "pi_event"),
    ("/tribes", "tribe"),
    ("/teams", "team"),
    ("/tags", "tag"),
    ("/program-board", "program_board"),
    ("/team-boards", "team_board"),
    ("/risks-board", "risks_board"),
    ("/goals-board", "goals_board"),
    ("/backlog-board", "backlog_board"),
    ("/pre-pi", "pre_pi"),
    ("/capacity", "capacity"),
    ("/pi-cycles", "pi_cycle"),
    ("/navigation", "navigation"),
)

_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "version_conflict",
    422: "validation_error",
    429: "rate_limited",
    499: "client_cancelled",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return str(getattr(route, "path", request.url.path))


def _object_type(route: str) -> str:
    if route.endswith("/auth/login") or route.endswith("/auth/logout") or route.endswith("/auth/me"):
        return "user_session"
    for marker, resource in _RESOURCE_MARKERS:
        if marker in route:
            return resource
    return "api_resource"


def _action_for(method: str, route: str, object_type: str) -> str:
    if route.endswith("/auth/login"):
        return "authentication.login"
    if route.endswith("/auth/logout"):
        return "authentication.logout"
    if route.endswith("/auth/me"):
        return "authentication.session_check"
    if route.endswith("/app/pi-cycles"):
        return "pi_cycle.select"
    if route.endswith("/dispatch") or route.endswith("/move"):
        return f"{object_type}.move"
    if route.endswith("/submit"):
        return f"{object_type}.submit"
    if route.endswith("/order"):
        return f"{object_type}.reorder"
    if route.endswith("/status"):
        return f"{object_type}.status_update"
    if "/links" in route:
        return f"{object_type}.unlink" if method == "DELETE" else f"{object_type}.link"
    operation = {
        "GET": "read",
        "HEAD": "read",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }.get(method, "execute")
    return f"{object_type}.{operation}"


def _primary_object_id(path_params: dict[str, Any]) -> str | None:
    identifiers = [(key, value) for key, value in path_params.items() if key.endswith("_id")]
    if not identifiers:
        return None
    non_cycle = [(key, value) for key, value in identifiers if key != "cycle_id"]
    return str((non_cycle or identifiers)[-1][1])


def _is_trusted_proxy(peer_ip: str | None, networks: list[str]) -> bool:
    if not peer_ip or not networks:
        return False
    try:
        address = ipaddress.ip_address(peer_ip)
        return any(address in ipaddress.ip_network(value, strict=False) for value in networks)
    except ValueError:
        return False


def source_ip(request: Request, trusted_proxy_networks: list[str]) -> str | None:
    peer_ip = request.client.host if request.client else None
    if _is_trusted_proxy(peer_ip, trusted_proxy_networks):
        forwarded_for = request.headers.get("x-forwarded-for", "")
        candidate = forwarded_for.split(",", 1)[0].strip()
        try:
            return str(ipaddress.ip_address(candidate)) if candidate else peer_ip
        except ValueError:
            return peer_ip
    return peer_ip


def _host_identity(configured_ip: str) -> tuple[str | None, str]:
    host_name = socket.gethostname()
    if configured_ip:
        return configured_ip, host_name
    try:
        return socket.gethostbyname(host_name), host_name
    except OSError:
        return None, host_name


def _session_id(token: str | None) -> str | None:
    if not token:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _description(action: str, result: str, method: str, route: str, status_code: int) -> str:
    return f"{action}: {result}; {method} {route}; HTTP {status_code}"


class AuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, settings: Settings):
        super().__init__(app)
        self.settings = settings
        self.host_ip, self.host_name = _host_identity(settings.audit_host_ip)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.settings.audit_enabled or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.url.path == "/api/health" or request.method == "OPTIONS":
            return await call_next(request)

        started_at = datetime.now(timezone.utc)
        started_monotonic = time.monotonic()
        request_id = uuid.uuid4()
        request.state.audit_username = None
        request.state.audit_auth_provider = None
        request.state.audit_error_code = None

        session_manager = get_session_manager()
        token = request.cookies.get(session_manager.settings.session_cookie_name)
        if token:
            try:
                user = session_manager.read(token)
                request.state.audit_username = user.username
                request.state.audit_auth_provider = user.provider
            except InvalidSession:
                request.state.audit_error_code = "invalid_session"
        request.state.audit_session_id = _session_id(token)

        response: Response | None = None
        raised_error: BaseException | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except asyncio.CancelledError as error:
            status_code = 499
            request.state.audit_error_code = "client_cancelled"
            raised_error = error
        except Exception as error:
            status_code = 500
            request.state.audit_error_code = "internal_error"
            raised_error = error

        finished_at = datetime.now(timezone.utc)
        route = _route_template(request)
        object_type = _object_type(route)
        action = _action_for(request.method, route, object_type)
        if status_code == 499:
            result = "cancelled"
        elif status_code < 400:
            result = "success"
        else:
            result = "failure"
        event = AuditEvent(
            event_id=uuid.uuid4(),
            occurred_at=finished_at,
            source_service=self.settings.audit_source_service,
            source_component="fastapi",
            environment=self.settings.app_env,
            username=request.state.audit_username,
            auth_provider=request.state.audit_auth_provider,
            source_ip=source_ip(request, self.settings.audit_trusted_proxy_network_list),
            host_ip=self.host_ip,
            host_name=self.host_name,
            operation_started_at=started_at,
            operation_finished_at=finished_at,
            duration_ms=max(0, round((time.monotonic() - started_monotonic) * 1000)),
            action=action,
            object_type=object_type,
            object_id=_primary_object_id(request.path_params),
            result=result,
            description=_description(action, result, request.method, route, status_code),
            request_id=request_id,
            session_id=request.state.audit_session_id,
            http_method=request.method,
            http_route=route,
            http_path=request.url.path,
            http_status=status_code,
            error_code=request.state.audit_error_code or _ERROR_CODES.get(status_code),
            details={
                "path_parameters": {key: str(value) for key, value in request.path_params.items()},
                "query_parameter_names": sorted(set(request.query_params.keys())),
            },
        )
        await self._persist_safely(request, event)

        if raised_error is not None:
            raise raised_error
        assert response is not None
        response.headers["X-Request-ID"] = str(request_id)
        return response

    async def _persist_safely(self, request: Request, event: AuditEvent) -> None:
        try:
            await request.app.state.audit_sink.write(event)
        except Exception as error:
            logger.error(
                "audit_database_write_failed event_id=%s error_type=%s",
                event.event_id,
                type(error).__name__,
            )
            logger.warning("audit_fallback %s", json.dumps(event.as_log_dict(), ensure_ascii=False))
