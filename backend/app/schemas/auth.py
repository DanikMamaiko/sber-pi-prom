import uuid

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=1000)


class CurrentUserRead(BaseModel):
    username: str
    roles: list[str]
    permissions: list[str]
    provider: str
    session_expires_at: int


class NavigationSectionRead(BaseModel):
    id: str
    name: str
    enabled: bool
    status: str | None = None
    message: str | None = None


class NavigationTabRead(BaseModel):
    id: str
    name: str
    can_read: bool = True
    can_write: bool = False
    can_approve: bool = False


class NavigationCycleRead(BaseModel):
    id: uuid.UUID
    year: int
    quarter: str


class NavigationCycleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=2026, le=2100)
    quarter: str = Field(pattern="^Q[1-4]$")


class NavigationRead(BaseModel):
    sections: list[NavigationSectionRead]
    tabs: list[NavigationTabRead]
    pi_cycles: list[NavigationCycleRead]
