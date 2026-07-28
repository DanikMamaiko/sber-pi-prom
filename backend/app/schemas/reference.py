import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.schemas._base import ORMModel


class TribeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)


class TribeRead(ORMModel):
    id: uuid.UUID
    name: str


class TeamCreate(BaseModel):
    tribe_id: uuid.UUID
    name: str = Field(min_length=1, max_length=180)
    team_type: str = Field(default="Agile", pattern="^(Agile|ИТ-проект)$")
    competencies: list[str] = Field(default_factory=lambda: ["SA", "DEV", "QA"])


class TeamRead(ORMModel):
    id: uuid.UUID
    tribe_id: uuid.UUID
    name: str
    team_type: str
    excluded_from_goals: bool


class TeamMemberCreate(BaseModel):
    team_id: uuid.UUID
    full_name: str
    competency: str
    rate: float = Field(default=1.0, ge=0, le=1)
    unavailable_ranges: dict[str, Any] = Field(default_factory=dict)
    ceremony_percent: float = Field(default=0, ge=0, le=100)
    risk_percent: float = Field(default=0, ge=0, le=100)
    efficiency_percent: float | None = Field(default=None, ge=0, le=100)


class TeamMemberRead(ORMModel):
    id: uuid.UUID
    team_id: uuid.UUID
    full_name: str
    competency: str
    rate: float
    unavailable_ranges: dict[str, Any]
    ceremony_percent: float
    risk_percent: float
    efficiency_percent: float | None


