import secrets
from abc import ABC, abstractmethod

from app.auth.models import AuthIdentity
from app.auth.permissions import VALID_ROLES


class AuthProviderUnavailable(RuntimeError):
    pass


class AuthProvider(ABC):
    name: str

    @abstractmethod
    async def authenticate(self, username: str, password: str) -> AuthIdentity | None:
        raise NotImplementedError


class LocalAuthProvider(AuthProvider):
    name = "local"

    def __init__(self, raw_users: str):
        self._users = self._parse_users(raw_users)

    @staticmethod
    def _parse_users(raw_users: str) -> dict[str, tuple[str, tuple[str, ...]]]:
        users: dict[str, tuple[str, tuple[str, ...]]] = {}
        for raw_record in raw_users.split(","):
            record = raw_record.strip()
            if not record:
                continue
            try:
                credentials, raw_roles = record.rsplit(":", 1)
                username, password = credentials.split(":", 1)
            except ValueError as error:
                raise ValueError(
                    "AUTH_TEST_USERS должен содержать записи username:password:role"
                ) from error
            username = username.strip()
            roles = tuple(dict.fromkeys(role.strip() for role in raw_roles.split("+") if role.strip()))
            if not username or not password or not roles:
                raise ValueError("AUTH_TEST_USERS содержит пустой логин, пароль или роль")
            unknown_roles = set(roles) - VALID_ROLES
            if unknown_roles:
                raise ValueError(
                    f"AUTH_TEST_USERS содержит неизвестные роли: {', '.join(sorted(unknown_roles))}"
                )
            if username in users:
                raise ValueError(f"AUTH_TEST_USERS содержит повторный логин: {username}")
            users[username] = (password, roles)
        if not users:
            raise ValueError("AUTH_TEST_USERS не содержит ни одного пользователя")
        return users

    async def authenticate(self, username: str, password: str) -> AuthIdentity | None:
        record = self._users.get(username.strip())
        if record is None or not secrets.compare_digest(record[0], password):
            return None
        return AuthIdentity(username=username.strip(), roles=record[1], provider=self.name)


class LdapAuthProvider(AuthProvider):
    """Extension point for the future LDAP/Active Directory integration."""

    name = "ldap"

    async def authenticate(self, username: str, password: str) -> AuthIdentity | None:
        raise AuthProviderUnavailable("LDAP/Active Directory provider ещё не реализован")
