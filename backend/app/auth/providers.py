import asyncio
import math
import secrets
from abc import ABC, abstractmethod

from ldap3 import SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException
from ldap3.core.results import RESULT_INVALID_CREDENTIALS
from ldap3.utils.conv import escape_filter_chars

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
    """Authenticate with LDAP and map direct AD groups to application roles."""

    name = "ldap"

    def __init__(
        self,
        *,
        url: str,
        user_search_base: str,
        user_filter: str,
        bind_dn: str,
        bind_password: str,
        role_groups: dict[str, str],
        use_tls: bool = False,
        connect_timeout_seconds: float = 5.0,
    ):
        required = {
            "LDAP_URL": url,
            "LDAP_USER_SEARCH_BASE": user_search_base,
            "LDAP_USER_FILTER": user_filter,
            "LDAP_BIND_DN": bind_dn,
            "LDAP_BIND_PASSWORD": bind_password,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"Не заполнены обязательные настройки LDAP: {', '.join(missing)}")
        if "{username}" not in user_filter:
            raise ValueError("LDAP_USER_FILTER должен содержать {username}")
        unknown_roles = set(role_groups) - VALID_ROLES
        if unknown_roles:
            raise ValueError(
                f"LDAP настроен с неизвестными ролями: {', '.join(sorted(unknown_roles))}"
            )
        empty_groups = [
            role for role, group_dn in role_groups.items() if not group_dn.strip()
        ]
        if empty_groups:
            raise ValueError(
                f"Не заполнены LDAP-группы для ролей: {', '.join(sorted(empty_groups))}"
            )

        self._server = Server(
            url.strip(),
            use_ssl=use_tls,
            connect_timeout=connect_timeout_seconds,
        )
        self._user_search_base = user_search_base.strip()
        self._user_filter = user_filter
        self._bind_dn = bind_dn.strip()
        self._bind_password = bind_password
        # ldap3 2.9.1 packs SO_RCVTIMEO as integer seconds on Linux.
        # Keep fractional connect timeouts, but round receive timeouts up.
        self._receive_timeout = max(1, math.ceil(connect_timeout_seconds))
        self._roles_by_group = {
            group_dn.strip().casefold(): role for role, group_dn in role_groups.items()
        }

    async def authenticate(self, username: str, password: str) -> AuthIdentity | None:
        username = username.strip()
        if not username or not password:
            return None
        return await asyncio.to_thread(self._authenticate_sync, username, password)

    def _authenticate_sync(self, username: str, password: str) -> AuthIdentity | None:
        service_connection = self._connection(self._bind_dn, self._bind_password)
        try:
            if not service_connection.bind():
                raise AuthProviderUnavailable(
                    "LDAP недоступен или техническая учётная запись отклонена"
                )

            search_filter = self._user_filter.replace(
                "{username}", escape_filter_chars(username)
            )
            if not service_connection.search(
                search_base=self._user_search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=["sAMAccountName", "memberOf"],
                size_limit=2,
                time_limit=max(1, int(self._receive_timeout)),
            ):
                raise AuthProviderUnavailable("LDAP не выполнил поиск пользователя")
            if len(service_connection.entries) != 1:
                return None

            entry = service_connection.entries[0]
            group_dns = {
                str(value).strip().casefold() for value in entry.memberOf.values
            }
            roles = tuple(
                role for group_dn, role in self._roles_by_group.items() if group_dn in group_dns
            )
            if not roles:
                return None

            user_connection = self._connection(entry.entry_dn, password)
            try:
                if not user_connection.bind():
                    result_code = user_connection.result.get("result")
                    if result_code == RESULT_INVALID_CREDENTIALS:
                        return None
                    raise AuthProviderUnavailable("LDAP не выполнил проверку учётных данных")
            finally:
                user_connection.unbind()

            ldap_username = username
            if "sAMAccountName" in entry and entry.sAMAccountName.value:
                ldap_username = str(entry.sAMAccountName.value)
            return AuthIdentity(username=ldap_username, roles=roles, provider=self.name)
        except AuthProviderUnavailable:
            raise
        except (LDAPException, OSError) as error:
            raise AuthProviderUnavailable("LDAP временно недоступен") from error
        finally:
            service_connection.unbind()

    def _connection(self, user: str, password: str) -> Connection:
        return Connection(
            self._server,
            user=user,
            password=password,
            receive_timeout=self._receive_timeout,
            raise_exceptions=False,
        )
