from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SberPI PI Cycle MVP"
    app_env: str = "local"
    database_url: str = Field(
        default="postgresql+asyncpg://sberpi:sberpi@localhost:5432/sberpi"
    )
    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080"
    auth_provider: str = "local"
    auth_test_users: str = (
        "admin:admin123:admin,"
        "editor:editor123:planning_editor,"
        "po_itl:poitl123:planning_editor,"
        "pm:pm123:business_viewer,"
        "user:user123:viewer"
    )
    session_secret: str = "local-development-only-change-me"
    session_ttl_minutes: int = Field(default=60, ge=1, le=1440)
    session_cookie_name: str = "sberpi_session"
    session_cookie_secure: bool = False

    jira_enabled: bool = False
    jira_base_url: str = "https://jira-apptst-ift.sigma-belpsb.by/jira"
    jira_username: str = ""
    jira_password: str = ""
    jira_verify_ssl: bool = True
    jira_ca_bundle: str = ""
    jira_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    jira_workday_hours: float = Field(default=8.0, gt=0.0, le=24.0)

    audit_enabled: bool = True
    # Empty means that audit events are stored in the main PostgreSQL database.
    # A separate URL remains supported for local development and legacy deployments.
    audit_database_url: str = ""
    audit_source_service: str = "sberpi-api"
    audit_host_ip: str = ""
    audit_trusted_proxy_networks: str = ""
    audit_connect_timeout_seconds: int = Field(default=3, ge=1, le=30)
    audit_retry_seconds: int = Field(default=30, ge=1, le=3600)

    ad_group_admin: str = (
        "CN=SberPI-Admins,OU=SberPI,OU=Groups for soft access,"
        "OU=Groups,OU=Tech,DC=belpsb,DC=by"
    )
    ad_group_planning_editor: str = (
        "CN=SberPI-PlanningEditors,OU=SberPI,OU=Groups for soft access,"
        "OU=Groups,OU=Tech,DC=belpsb,DC=by"
    )
    ad_group_business_viewer: str = (
        "CN=SberPI-BusinessViewers,OU=SberPI,OU=Groups for soft access,"
        "OU=Groups,OU=Tech,DC=belpsb,DC=by"
    )
    ad_group_viewer: str = (
        "CN=SberPI-Viewers,OU=SberPI,OU=Groups for soft access,"
        "OU=Groups,OU=Tech,DC=belpsb,DC=by"
    )

    ldap_url: str = "ldap://belpsb.by:389"
    ldap_base_dn: str = "DC=belpsb,DC=by"
    ldap_user_search_base: str = "OU=Users ALL,DC=belpsb,DC=by"
    ldap_user_filter: str = "(cn={username})"
    ldap_group_search_base: str = "OU=Groups,OU=Tech,DC=belpsb,DC=by"
    ldap_group_filter: str = "(member={user_dn})"
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_use_tls: bool = False
    ldap_connect_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def audit_trusted_proxy_network_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.audit_trusted_proxy_networks.split(",")
            if item.strip()
        ]

    @property
    def effective_audit_database_url(self) -> str:
        return self.audit_database_url.strip() or self.database_url

    @property
    def jira_is_configured(self) -> bool:
        return bool(
            self.jira_enabled
            and self.jira_base_url.strip()
            and self.jira_username.strip()
            and self.jira_password
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
