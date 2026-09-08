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
        provider = LdapAuthProvider(
            url=settings.ldap_url,
            user_search_base=settings.ldap_user_search_base,
            user_filter=settings.ldap_user_filter,
            bind_dn=settings.ldap_bind_dn,
            bind_password=settings.ldap_bind_password,
            use_tls=settings.ldap_use_tls,
            connect_timeout_seconds=settings.ldap_connect_timeout_seconds,
            role_groups={
                "admin": settings.ad_group_admin,
                "planning_editor": settings.ad_group_planning_editor,
                "business_viewer": settings.ad_group_business_viewer,
                "viewer": settings.ad_group_viewer,
            },
        )
    else:
        raise ValueError(f"Неизвестный AUTH_PROVIDER: {settings.auth_provider}")
    return AuthService(provider)
