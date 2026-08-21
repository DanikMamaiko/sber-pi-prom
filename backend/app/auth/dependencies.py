from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from app.auth.models import CurrentUser
from app.auth.session import InvalidSession, SessionManager, get_session_manager


async def require_auth(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager),
) -> CurrentUser:
    token = request.cookies.get(session_manager.settings.session_cookie_name)
    if not token:
        request.state.audit_error_code = "missing_session"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    try:
        user = session_manager.read(token)
        request.state.audit_username = user.username
        request.state.audit_auth_provider = user.provider
        return user
    except InvalidSession as error:
        request.state.audit_error_code = "invalid_session"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла или недействительна",
        ) from error


def ensure_permission(user: CurrentUser, permission: str) -> None:
    if permission not in user.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")


def require_permission(permission: str) -> Callable:
    async def dependency(
        request: Request,
        user: CurrentUser = Depends(require_auth),
    ) -> CurrentUser:
        try:
            ensure_permission(user, permission)
        except HTTPException:
            request.state.audit_error_code = "permission_denied"
            raise
        return user

    return dependency


def require_any_permission(*permissions: str) -> Callable:
    async def dependency(
        request: Request,
        user: CurrentUser = Depends(require_auth),
    ) -> CurrentUser:
        if not any(permission in user.permissions for permission in permissions):
            request.state.audit_error_code = "permission_denied"
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return user

    return dependency


def require_http_permission(read_permission: str, write_permission: str) -> Callable:
    async def dependency(
        request: Request,
        user: CurrentUser = Depends(require_auth),
    ) -> CurrentUser:
        permission = read_permission if request.method in {"GET", "HEAD"} else write_permission
        try:
            ensure_permission(user, permission)
        except HTTPException:
            request.state.audit_error_code = "permission_denied"
            raise
        return user

    return dependency
