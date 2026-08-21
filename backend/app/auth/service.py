from functools import lru_cache

from app.auth.models import AuthIdentity
from app.auth.providers import AuthProvider, LdapAuthProvider, LocalAuthProvider
from app.core.config import get_settings


class AuthService:
    def __init__(self, provider: AuthProvider):
        self.provider = provider

    async def authenticate(self, username: str, password: str) -> AuthIdentity | None:
        return await self.provider.authenticate(username, password)


@lru_cache
def get_auth_service() -> AuthService:
    settings = get_settings()
    provider_name = settings.auth_provider.strip().lower()
    if provider_name == "local":
        provider: AuthProvider = LocalAuthProvider(settings.auth_test_users)
    elif provider_name == "ldap":
        provider = LdapAuthProvider()
    else:
        raise ValueError(f"Неизвестный AUTH_PROVIDER: {settings.auth_provider}")
    return AuthService(provider)
