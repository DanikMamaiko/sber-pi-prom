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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    try:
        return session_manager.read(token)
    except InvalidSession as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла или недействительна",
        ) from error


def ensure_permission(user: CurrentUser, permission: str) -> None:
    if permission not in user.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")


def require_permission(permission: str) -> Callable:
    async def dependency(user: CurrentUser = Depends(require_auth)) -> CurrentUser:
        ensure_permission(user, permission)
        return user

    return dependency


def require_any_permission(*permissions: str) -> Callable:
    async def dependency(user: CurrentUser = Depends(require_auth)) -> CurrentUser:
        if not any(permission in user.permissions for permission in permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return user

    return dependency


def require_http_permission(read_permission: str, write_permission: str) -> Callable:
    async def dependency(
        request: Request,
        user: CurrentUser = Depends(require_auth),
    ) -> CurrentUser:
        permission = read_permission if request.method in {"GET", "HEAD"} else write_permission
        ensure_permission(user, permission)
        return user

    return dependency
