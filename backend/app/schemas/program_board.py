import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProgramBoardEndpoint(BaseModel):
    kind: str = Field(pattern="^(c|g|w)$")
    ref: str = Field(min_length=1, max_length=80)


class ProgramBoardBend(BaseModel):
    dx: float
    dy: float


class ProgramBoardConnectionWrite(BaseModel):
    id: uuid.UUID | None = None
    client_uid: str = Field(min_length=1, max_length=80)
    source: ProgramBoardEndpoint
    target: ProgramBoardEndpoint
    relation_type: str = Field(default="depends_on", max_length=40)
    bend: ProgramBoardBend | None = None
    sort_order: int = Field(default=0, ge=0)


class ProgramBoardConnectionRead(ProgramBoardConnectionWrite):
    id: uuid.UUID


class ProgramBoardWrite(BaseModel):
    expected_version: int = Field(ge=0)
    connections: list[ProgramBoardConnectionWrite] = Field(default_factory=list)


class ProgramBoardRead(BaseModel):
    initialized: bool
    version: int
    cycle_id: uuid.UUID
    cycle_status: str
    sprints: list["ProgramBoardSprint"] = Field(default_factory=list)
    tribes: list["ProgramBoardTribe"] = Field(default_factory=list)
    teams: list["ProgramBoardTeam"] = Field(default_factory=list)
    cards: list["ProgramBoardCard"] = Field(default_factory=list)
    connections: list[ProgramBoardConnectionRead] = Field(default_factory=list)
    conflicts: list["ProgramBoardConflict"] = Field(default_factory=list)


class ProgramBoardEvent(BaseModel):
    id: uuid.UUID
    name: str
    event_date: date
    end_date: date | None
    event_type: str


class ProgramBoardSprint(BaseModel):
    index: int
    number: int
    start_date: date
    end_date: date
    events: list[ProgramBoardEvent] = Field(default_factory=list)


class ProgramBoardTribe(BaseModel):
    id: uuid.UUID
    name: str
    sort_order: int


class ProgramBoardTeam(BaseModel):
    id: uuid.UUID
    tribe_id: uuid.UUID
    tribe: str
    name: str
    sort_order: int


class ProgramBoardExecutor(BaseModel):
    team_id: uuid.UUID
    team: str
    effort_by_competency: dict[str, float] = Field(default_factory=dict)
    total_effort: float


class ProgramBoardCard(BaseModel):
    id: uuid.UUID
    issue_key: str
    title: str
    initiative_type: str
    owner_team_id: uuid.UUID | None
    owner_team: str
    primary_team_id: uuid.UUID
    primary_team: str
    primary_tribe_id: uuid.UUID
    primary_tribe: str
    executors: list[ProgramBoardExecutor] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sprint_index: int | None
    week_index: int | None
    board_sort_order: int
    agreed: bool
    visual_state: Literal["blue", "purple", "red"]
    total_effort: float
    conflict_codes: list[str] = Field(default_factory=list)


class ProgramBoardConflict(BaseModel):
    code: str
    severity: Literal["warning", "error"] = "warning"
    message: str
    initiative_id: uuid.UUID | None = None
    connection_id: uuid.UUID | None = None


class ProgramBoardCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)


class ProgramBoardMoveCommand(ProgramBoardCommand):
    sprint_index: int = Field(ge=0)
    sort_order: int = Field(default=0, ge=0)


class ProgramBoardEndpointId(BaseModel):
    kind: Literal["initiative", "story", "work_item"]
    id: uuid.UUID


class ProgramBoardConnectionCreate(ProgramBoardCommand):
    source: ProgramBoardEndpointId
    target: ProgramBoardEndpointId
    relation_type: str = Field(default="depends_on", min_length=1, max_length=40)
    bend: ProgramBoardBend | None = None


class ProgramBoardConnectionUpdate(ProgramBoardCommand):
    source: ProgramBoardEndpointId | None = None
    target: ProgramBoardEndpointId | None = None
    relation_type: str | None = Field(default=None, min_length=1, max_length=40)
    bend: ProgramBoardBend | None = None
    clear_bend: bool = False


ProgramBoardRead.model_rebuild()


