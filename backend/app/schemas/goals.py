import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._base import ORMModel


class GoalsItemWrite(BaseModel):
    id: uuid.UUID | None = None
    tribe: str = Field(default="", max_length=180)
    team: str = Field(default="", max_length=180)
    issue_key: str = Field(default="", max_length=80)
    initiative_title: str = Field(default="", max_length=260)
    goal_text: str = Field(default="", max_length=260)
    product: str = Field(default="", max_length=180)
    metric: str = Field(default="", max_length=260)
    current_value: str = Field(default="", max_length=260)
    target_value: str = Field(default="", max_length=260)
    hypothesis: str = ""
    redesign: str = ""
    tribe_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    initiative_id: uuid.UUID | None = None
    initiative_ids: list[uuid.UUID] = Field(default_factory=list)
    title: str = Field(default="", max_length=260)
    owner: str = Field(default="", max_length=220)
    business_value: int | None = Field(default=None, ge=0, le=100)
    status: Literal["planned", "in_progress", "done", "cancelled"] = "planned"
    category: Literal["committed", "stretch"] = "committed"
    sort_order: int = Field(default=0, ge=0)


class GoalsItemRead(GoalsItemWrite):
    id: uuid.UUID


class GoalsWrite(BaseModel):
    expected_version: int = Field(ge=0)
    goals: list[GoalsItemWrite] = Field(default_factory=list)


class GoalsRead(BaseModel):
    initialized: bool
    version: int
    goals: list[GoalsItemRead] = Field(default_factory=list)
    reference_data: dict[str, Any] = Field(default_factory=dict)


class GoalCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)


class GoalFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tribe_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=260)
    product: str = Field(default="", max_length=180)
    metric: str = Field(default="", max_length=260)
    current_value: str = Field(default="", max_length=260)
    target_value: str = Field(default="", max_length=260)
    hypothesis: str = ""
    redesign: str = ""
    owner: str = Field(default="", max_length=220)
    business_value: int | None = Field(default=None, ge=0, le=100)
    status: Literal["planned", "in_progress", "done", "cancelled"] = "planned"
    category: Literal["committed", "stretch"] = "committed"
    initiative_ids: list[uuid.UUID] = Field(default_factory=list)
    confirm_cascade: bool = False


class GoalCreateCommand(GoalCommand, GoalFields):
    pass


class GoalUpdateCommand(GoalCommand):
    tribe_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=260)
    product: str | None = Field(default=None, max_length=180)
    metric: str | None = Field(default=None, max_length=260)
    current_value: str | None = Field(default=None, max_length=260)
    target_value: str | None = Field(default=None, max_length=260)
    hypothesis: str | None = None
    redesign: str | None = None
    owner: str | None = Field(default=None, max_length=220)
    business_value: int | None = Field(default=None, ge=0, le=100)
    status: Literal["planned", "in_progress", "done", "cancelled"] | None = None
    category: Literal["committed", "stretch"] | None = None
    initiative_ids: list[uuid.UUID] | None = None
    confirm_cascade: bool = False


class GoalDeleteCommand(GoalCommand):
    confirm_cascade: bool = False


class GoalReorderCommand(GoalCommand):
    goal_ids: list[uuid.UUID] = Field(min_length=1)


class GoalStatusCommand(GoalCommand):
    status: Literal["planned", "in_progress", "done", "cancelled"]


class GoalLinkCommand(GoalCommand):
    initiative_id: uuid.UUID
    confirm_cascade: bool = False


class GoalUnlinkCommand(GoalCommand):
    confirm_cascade: bool = False


class PiGoalCreate(BaseModel):
    tribe_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    initiative_id: uuid.UUID | None = None
    title: str
    metric: str = ""
    current_value: str = ""
    target_value: str = ""
    hypothesis: str = ""
    redesign: str = ""
    product: str = ""


class PiGoalRead(ORMModel):
    id: uuid.UUID
    cycle_id: uuid.UUID
    tribe_id: uuid.UUID | None
    team_id: uuid.UUID | None
    initiative_id: uuid.UUID | None
    title: str
    metric: str
    current_value: str
    target_value: str
    product: str
    sort_order: int


