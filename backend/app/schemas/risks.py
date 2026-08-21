import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._base import ORMModel


class RiskCreate(BaseModel):
    scope: str = Field(default="general", pattern="^(general|team)$")
    team_id: uuid.UUID | None = None
    is_shared: bool = False
    description: str = Field(min_length=1)
    owner: str = ""
    impact: str = ""
    control_point: str = ""
    mitigation_plan: str = ""


class RiskRead(ORMModel):
    id: uuid.UUID
    cycle_id: uuid.UUID
    scope: str
    team_id: uuid.UUID | None
    is_shared: bool
    description: str
    owner: str
    impact: str
    control_point: str
    mitigation_plan: str


class RiskTeamRef(BaseModel):
    tribe: str = Field(min_length=1, max_length=180)
    name: str = Field(min_length=1, max_length=180)


class RiskItemWrite(BaseModel):
    id: uuid.UUID | None = None
    client_uid: str = Field(min_length=1, max_length=80)
    scope: str = Field(pattern="^(general|team|tribe|initiative)$")
    team: RiskTeamRef | None = None
    tribe_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    initiative_id: uuid.UUID | None = None
    is_shared: bool = False
    description: str = Field(min_length=1)
    owner: str = Field(default="", max_length=220)
    impact: str = ""
    control_point: str = Field(default="", max_length=220)
    mitigation_plan: str = ""
    probability: int = Field(default=1, ge=1, le=5)
    impact_level: int = Field(default=1, ge=1, le=5)
    reaction_due_date: date | None = None
    treatment_plan: str = ""
    status: Literal["open", "watching", "closed"] = "open"
    roam: Literal["resolved", "owned", "accepted", "mitigated"] | None = None
    sort_order: int = Field(default=0, ge=0)


class RiskItemRead(RiskItemWrite):
    id: uuid.UUID
    criticality: int = 1
    criticality_label: str = "low"
    link: dict[str, Any] | None = None


class RisksWrite(BaseModel):
    expected_version: int = Field(ge=0)
    risks: list[RiskItemWrite] = Field(default_factory=list)


class RisksRead(BaseModel):
    initialized: bool
    version: int
    risks: list[RiskItemRead] = Field(default_factory=list)
    reference_data: dict[str, Any] = Field(default_factory=dict)


class RiskCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)


class RiskFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["general", "team", "tribe", "initiative"] = "general"
    tribe_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    initiative_id: uuid.UUID | None = None
    is_shared: bool = False
    description: str = Field(min_length=1)
    owner: str = Field(default="", max_length=220)
    impact: str = ""
    control_point: str = Field(default="", max_length=220)
    mitigation_plan: str = ""
    probability: int = Field(default=1, ge=1, le=5)
    impact_level: int = Field(default=1, ge=1, le=5)
    reaction_due_date: date | None = None
    treatment_plan: str = ""
    status: Literal["open", "watching", "closed"] = "open"
    roam: Literal["resolved", "owned", "accepted", "mitigated"] | None = None


class RiskCreateCommand(RiskCommand, RiskFields):
    pass


class RiskUpdateCommand(RiskCommand):
    scope: Literal["general", "team", "tribe", "initiative"] | None = None
    tribe_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    initiative_id: uuid.UUID | None = None
    is_shared: bool | None = None
    description: str | None = Field(default=None, min_length=1)
    owner: str | None = Field(default=None, max_length=220)
    impact: str | None = None
    control_point: str | None = Field(default=None, max_length=220)
    mitigation_plan: str | None = None
    probability: int | None = Field(default=None, ge=1, le=5)
    impact_level: int | None = Field(default=None, ge=1, le=5)
    reaction_due_date: date | None = None
    treatment_plan: str | None = None
    status: Literal["open", "watching", "closed"] | None = None
    roam: Literal["resolved", "owned", "accepted", "mitigated"] | None = None


class RiskDeleteCommand(RiskCommand):
    pass


class RiskReorderCommand(RiskCommand):
    risk_ids: list[uuid.UUID] = Field(min_length=1)


class RiskStatusCommand(RiskCommand):
    status: Literal["open", "watching", "closed"]


class RiskRoamCommand(RiskCommand):
    roam: Literal["resolved", "owned", "accepted", "mitigated"] | None


class RiskLinkCommand(RiskCommand):
    scope: Literal["general", "team", "tribe", "initiative"]
    tribe_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    initiative_id: uuid.UUID | None = None


