import time
from functools import lru_cache

from fastapi import Response
from itsdangerous import BadSignature, URLSafeSerializer

from app.auth.models import AuthIdentity, CurrentUser
from app.auth.permissions import permissions_for_roles
from app.core.config import Settings, get_settings


class InvalidSession(ValueError):
    pass


class SessionManager:
    salt = "sberpi-http-session-v1"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.serializer = URLSafeSerializer(settings.session_secret, salt=self.salt)

    def create(self, identity: AuthIdentity, *, now: int | None = None) -> tuple[str, CurrentUser]:
        issued_at = int(time.time()) if now is None else int(now)
        expires_at = issued_at + self.settings.session_ttl_minutes * 60
        payload = {
            "v": 1,
            "username": identity.username,
            "roles": list(identity.roles),
            "provider": identity.provider,
            "issued_at": issued_at,
            "expires_at": expires_at,
        }
        return self.serializer.dumps(payload), self._current_user(payload, now=issued_at)

    def read(self, token: str, *, now: int | None = None) -> CurrentUser:
        try:
            payload = self.serializer.loads(token)
        except BadSignature as error:
            raise InvalidSession("Некорректная подпись сессии") from error
        return self._current_user(payload, now=now)

    def _current_user(self, payload: object, *, now: int | None = None) -> CurrentUser:
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise InvalidSession("Некорректный формат сессии")
        current_time = int(time.time()) if now is None else int(now)
        try:
            username = str(payload["username"]).strip()
            roles = tuple(str(role) for role in payload["roles"])
            provider = str(payload["provider"])
            issued_at = int(payload["issued_at"])
            expires_at = int(payload["expires_at"])
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidSession("Некорректный формат сессии") from error
        if not username or issued_at > current_time + 60 or current_time >= expires_at:
            raise InvalidSession("Сессия истекла или недействительна")
        try:
            permissions = permissions_for_roles(roles)
        except ValueError as error:
            raise InvalidSession("Сессия содержит неизвестную роль") from error
        return CurrentUser(
            username=username,
            roles=roles,
            permissions=permissions,
            provider=provider,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    def set_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            key=self.settings.session_cookie_name,
            value=token,
            max_age=self.settings.session_ttl_minutes * 60,
            httponly=True,
            secure=self.settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(
            key=self.settings.session_cookie_name,
            httponly=True,
            secure=self.settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )


@lru_cache
def get_session_manager() -> SessionManager:
    return SessionManager(get_settings())
