import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._base import ORMModel
from app.schemas.backlog import BacklogExecutorPayload
from app.schemas.goals import GoalsRead


class InitiativeCreate(BaseModel):
    issue_key: str = Field(min_length=1, max_length=80)
    title: str = Field(max_length=260)
    description: str = ""
    product: str = ""
    owner_team_id: uuid.UUID | None = None
    initiative_type: str = ""
    status: str = Field(default="backlog", pattern="^(backlog|planned|on_board|done)$")
    goal_text: str = ""
    metric: str = ""
    current_value: str = ""
    target_value: str = ""
    hypothesis: str = ""
    redesign: str = ""
    sprint_index: int | None = None
    week_index: int | None = None
    executors: list[BacklogExecutorPayload] = Field(default_factory=list)


class InitiativeRead(ORMModel):
    id: uuid.UUID
    cycle_id: uuid.UUID
    issue_key: str
    title: str
    description: str
    product: str
    owner_team_id: uuid.UUID | None
    initiative_type: str
    status: str
    goal_text: str
    metric: str
    current_value: str
    target_value: str
    hypothesis: str
    redesign: str
    customer_priority: str
    team_priority: str
    estimate: str
    comment: str
    pre_planned: bool
    on_board: bool
    agreed: bool
    tags: list[str]
    sprint_index: int | None
    week_index: int | None
    sort_order: int


class PrePiAttraction(BaseModel):
    id: uuid.UUID | None = None
    target_initiative_id: uuid.UUID | None = None
    issue_key: str = Field(default="", max_length=80)
    target_team_id: uuid.UUID | None = None
    team: str = Field(default="", max_length=180)
    sprint_index: int | None = Field(default=None, ge=0)
    approval_status: Literal["pending", "approved", "rejected"] = "pending"
    visual_state: str = "purple"
    sort_order: int = Field(default=0, ge=0)


class PrePiExecutor(BaseModel):
    id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    team: str = Field(min_length=1, max_length=180)
    tribe: str = Field(default="", max_length=180)
    effort_by_competency: dict[str, float] = Field(default_factory=dict)
    attractions: list[PrePiAttraction] = Field(default_factory=list)
    sort_order: int = Field(default=0, ge=0)


class PrePiInitiativeWrite(BaseModel):
    id: uuid.UUID | None = None
    issue_key: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=260)
    description: str = ""
    product: str = Field(default="", max_length=180)
    owner_team: str = Field(default="", max_length=180)
    owner_tribe: str = Field(default="", max_length=180)
    initiative_type: str = Field(default="", max_length=120)
    status: str = Field(default="backlog", pattern="^(backlog|planned|on_board|done)$")
    goal_text: str = Field(default="", max_length=260)
    metric: str = Field(default="", max_length=260)
    current_value: str = Field(default="", max_length=260)
    target_value: str = Field(default="", max_length=260)
    hypothesis: str = ""
    redesign: str = ""
    customer_priority: str = Field(default="", max_length=40)
    team_priority: str = Field(default="", max_length=40)
    estimate: str = Field(default="", max_length=120)
    comment: str = ""
    pre_planned: bool = False
    on_board: bool = False
    agreed: bool = False
    tags: list[str] = Field(default_factory=list)
    sprint_index: int | None = Field(default=None, ge=0)
    week_index: int | None = Field(default=None, ge=0)
    sort_order: int = Field(default=0, ge=0)
    executors: list[PrePiExecutor] = Field(default_factory=list)


class PrePiInitiativeRead(PrePiInitiativeWrite):
    id: uuid.UUID
    total_estimate: float = 0
    block: Literal["planned", "backlog"] = "backlog"
    required_fields: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)


class PrePiWrite(BaseModel):
    expected_version: int = Field(ge=0)
    initiatives: list[PrePiInitiativeWrite] = Field(default_factory=list)


class PrePiRead(BaseModel):
    initialized: bool
    version: int
    cycle: dict[str, Any] = Field(default_factory=dict)
    tribes: list[dict[str, Any]] = Field(default_factory=list)
    teams: list[dict[str, Any]] = Field(default_factory=list)
    goal_options: list[dict[str, Any]] = Field(default_factory=list)
    initiatives: list[PrePiInitiativeRead] = Field(default_factory=list)
    planned: list[PrePiInitiativeRead] = Field(default_factory=list)
    backlog: list[PrePiInitiativeRead] = Field(default_factory=list)
    capacity: dict[str, Any] = Field(default_factory=dict)
    tech_agenda: dict[str, Any] = Field(default_factory=dict)
    reg_agenda: dict[str, Any] = Field(default_factory=dict)
    allowed_values: dict[str, Any] = Field(default_factory=dict)


class PrePiInitiativeCommand(BaseModel):
    """One atomic edit of an initiative and its executor subgraph."""

    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    title: str | None = Field(default=None, max_length=260)
    description: str | None = None
    product: str | None = Field(default=None, max_length=180)
    owner_team_id: uuid.UUID | None = None
    initiative_type: str | None = Field(default=None, max_length=120)
    status: Literal["backlog", "planned", "on_board", "done"] | None = None
    goal_text: str | None = Field(default=None, max_length=260)
    metric: str | None = Field(default=None, max_length=260)
    current_value: str | None = Field(default=None, max_length=260)
    target_value: str | None = Field(default=None, max_length=260)
    hypothesis: str | None = None
    redesign: str | None = None
    customer_priority: str | None = Field(default=None, max_length=40)
    team_priority: str | None = Field(default=None, max_length=40)
    comment: str | None = None
    tags: list[str] | None = None
    executors: list[PrePiExecutor] | None = None


class PrePiMoveCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    target_block: Literal["planned", "backlog"]
    before_id: uuid.UUID | None = None
    confirm_cascade: bool = False


class PrePiDeleteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    confirm_cascade: bool = False


class PrePiSubmitTeam(BaseModel):
    tribe: str = Field(min_length=1, max_length=180)
    name: str = Field(min_length=1, max_length=180)


class PrePiSubmitWrite(BaseModel):
    expected_version: int = Field(ge=0)
    teams: list[PrePiSubmitTeam] = Field(min_length=1)


class PrePiSubmitRead(BaseModel):
    version: int
    goals_added: int
    board_added: int
    attractions_added: int
    pre_pi: PrePiRead
    goals: GoalsRead


