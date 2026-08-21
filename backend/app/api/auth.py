import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.dependencies import require_auth
from app.auth.models import CurrentUser
from app.auth.providers import AuthProviderUnavailable
from app.auth.service import AuthService, get_auth_service
from app.auth.session import SessionManager, get_session_manager
from app.schemas.auth import CurrentUserRead, LoginRequest


router = APIRouter(prefix="/auth", tags=["Auth"])


def _user_read(user: CurrentUser) -> CurrentUserRead:
    return CurrentUserRead(
        username=user.username,
        roles=list(user.roles),
        permissions=sorted(user.permissions),
        provider=user.provider,
        session_expires_at=user.expires_at,
    )


@router.post("/login", response_model=CurrentUserRead)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    session_manager: SessionManager = Depends(get_session_manager),
):
    request.state.audit_username = payload.username.strip()
    try:
        identity = await auth_service.authenticate(payload.username, payload.password)
    except AuthProviderUnavailable as error:
        request.state.audit_error_code = "auth_provider_unavailable"
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    if identity is None:
        request.state.audit_error_code = "invalid_credentials"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    token, user = session_manager.create(identity)
    request.state.audit_username = user.username
    request.state.audit_auth_provider = user.provider
    request.state.audit_session_id = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session_manager.set_cookie(response, token)
    return _user_read(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    _user: CurrentUser = Depends(require_auth),
    session_manager: SessionManager = Depends(get_session_manager),
) -> None:
    session_manager.clear_cookie(response)


@router.get("/me", response_model=CurrentUserRead)
async def me(user: CurrentUser = Depends(require_auth)) -> CurrentUserRead:
    return _user_read(user)
