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
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
