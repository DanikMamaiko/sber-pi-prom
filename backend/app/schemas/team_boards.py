import uuid
from datetime import date

from pydantic import BaseModel, Field, field_validator


class TeamBoardStoryWrite(BaseModel):
    id: uuid.UUID | None = None
    client_uid: str = Field(min_length=1, max_length=80)
    external_key: str = Field(default="", max_length=80)
    title: str = Field(default="", max_length=260)
    effort_by_competency: dict[str, float] = Field(default_factory=dict)
    sprint_index: int | None = Field(default=None, ge=0)
    week_index: int | None = Field(default=None, ge=0, le=1)
    sort_order: int = Field(default=0, ge=0)
    board_sort_order: int = Field(default=0, ge=0)


class TeamBoardStoryRead(TeamBoardStoryWrite):
    id: uuid.UUID


class TeamBoardWorkItemWrite(BaseModel):
    id: uuid.UUID | None = None
    client_uid: str = Field(min_length=1, max_length=80)
    story_client_uid: str | None = Field(default=None, max_length=80)
    assignee_member_id: uuid.UUID | None = None
    assignee_name: str = Field(default="", max_length=220)
    competency: str = Field(min_length=1, max_length=32)
    effort: float = Field(default=0, ge=0)
    sprint_index: int | None = Field(default=None, ge=0)
    week_index: int | None = Field(default=None, ge=0, le=1)
    sort_order: int = Field(default=0, ge=0)
    board_sort_order: int = Field(default=0, ge=0)


class TeamBoardWorkItemRead(TeamBoardWorkItemWrite):
    id: uuid.UUID


class TeamBoardInitiativeWrite(BaseModel):
    id: uuid.UUID | None = None
    issue_key: str = Field(min_length=1, max_length=80)
    pre_planned: bool = False
    on_board: bool = False
    agreed: bool = False
    sprint_index: int | None = Field(default=None, ge=0)
    week_index: int | None = Field(default=None, ge=0, le=1)
    board_sort_order: int = Field(default=0, ge=0)
    stories: list[TeamBoardStoryWrite] = Field(default_factory=list)
    work_items: list[TeamBoardWorkItemWrite] = Field(default_factory=list)


class TeamBoardInitiativeRead(TeamBoardInitiativeWrite):
    id: uuid.UUID
    stories: list[TeamBoardStoryRead] = Field(default_factory=list)
    work_items: list[TeamBoardWorkItemRead] = Field(default_factory=list)


class TeamBoardsWrite(BaseModel):
    expected_version: int = Field(ge=0)
    initiatives: list[TeamBoardInitiativeWrite] = Field(default_factory=list)


class TeamBoardsRead(BaseModel):
    initialized: bool
    version: int
    initiatives: list[TeamBoardInitiativeRead] = Field(default_factory=list)


class TeamBoardCommand(BaseModel):
    expected_version: int = Field(ge=0)


class TeamBoardInitiativeCommand(TeamBoardCommand):
    title: str | None = Field(default=None, max_length=260)
    initiative_type: str | None = Field(default=None, max_length=120)
    comment: str | None = None
    tags: list[str] | None = None
    effort_by_competency: dict[str, float] | None = None
    agreed: bool | None = None
    sprint_index: int | None = Field(default=None, ge=0)
    week_index: int | None = Field(default=None, ge=0, le=1)
    board_sort_order: int | None = Field(default=None, ge=0)


class TeamBoardStoryCreate(TeamBoardCommand, TeamBoardStoryWrite):
    id: None = None


class TeamBoardStoryUpdate(TeamBoardCommand):
    external_key: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, max_length=260)
    effort_by_competency: dict[str, float] | None = None
    sprint_index: int | None = Field(default=None, ge=0)
    week_index: int | None = Field(default=None, ge=0, le=1)
    sort_order: int | None = Field(default=None, ge=0)
    board_sort_order: int | None = Field(default=None, ge=0)


class TeamBoardDeleteCommand(TeamBoardCommand):
    confirm_cascade: bool = False


class TeamBoardWorkItemCreate(TeamBoardCommand, TeamBoardWorkItemWrite):
    id: None = None


class TeamBoardWorkItemUpdate(TeamBoardCommand):
    story_client_uid: str | None = Field(default=None, max_length=80)
    assignee_member_id: uuid.UUID | None = None
    assignee_name: str | None = Field(default=None, max_length=220)
    competency: str | None = Field(default=None, min_length=1, max_length=32)
    effort: float | None = Field(default=None, ge=0)
    sprint_index: int | None = Field(default=None, ge=0)
    week_index: int | None = Field(default=None, ge=0, le=1)
    sort_order: int | None = Field(default=None, ge=0)
    board_sort_order: int | None = Field(default=None, ge=0)


class CapacityDateRange(BaseModel):
    start: date
    end: date


class CapacityMemberWrite(BaseModel):
    id: uuid.UUID | None = None
    client_uid: str = Field(min_length=1, max_length=80)
    full_name: str = Field(min_length=1, max_length=220)
    competency: str = Field(min_length=1, max_length=32)
    rate: float = Field(default=1, ge=0, le=1)
    vacation_ranges: list[CapacityDateRange] = Field(default_factory=list)
    extra_unavailable_ranges: list[CapacityDateRange] = Field(default_factory=list)
    ceremony_percent: float = Field(default=0, ge=0, le=100)
    risk_percent: float = Field(default=0, ge=0, le=100)
    efficiency: float | None = Field(default=None, ge=0, le=1)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("ФИО не может быть пустым")
        return value


class CapacitySprintRead(BaseModel):
    sprint_index: int
    workdays: int
    planned_capacity: float
    vacation_days: int
    extra_unavailable_days: int
    available_capacity: float


class CapacityWeekRead(BaseModel):
    week_index: int = Field(ge=0, le=1)
    workdays: int
    planned_capacity: float
    vacation_days: int
    extra_unavailable_days: int
    available_capacity: float


class CapacityMemberRead(CapacityMemberWrite):
    id: uuid.UUID
    calendar_capacity: float
    available_capacity: float
    sprints: list[CapacitySprintRead] = Field(default_factory=list)
    weeks: dict[int, list[CapacityWeekRead]] = Field(default_factory=dict)


class CapacityTeamWrite(BaseModel):
    tribe: str = Field(min_length=1, max_length=180)
    team: str = Field(min_length=1, max_length=180)
    members: list[CapacityMemberWrite] = Field(default_factory=list)


class CapacityTeamRead(CapacityTeamWrite):
    members: list[CapacityMemberRead] = Field(default_factory=list)
    calendar_capacity: float
    available_capacity: float
    planned_effort: float
    available_by_competency: dict[str, float] = Field(default_factory=dict)
    planned_by_competency: dict[str, float] = Field(default_factory=dict)
    load_by_competency: dict[str, float] = Field(default_factory=dict)
    load_by_sprint: dict[int, dict[str, float]] = Field(default_factory=dict)
    load_by_week: dict[int, dict[int, dict[str, float]]] = Field(default_factory=dict)


class CapacityWrite(BaseModel):
    expected_version: int = Field(ge=0)
    teams: list[CapacityTeamWrite] = Field(default_factory=list)


class CapacityRead(BaseModel):
    initialized: bool
    version: int
    teams: list[CapacityTeamRead] = Field(default_factory=list)


class CapacityMemberCreate(TeamBoardCommand, CapacityMemberWrite):
    id: None = None
    tribe: str = Field(min_length=1, max_length=180)
    team: str = Field(min_length=1, max_length=180)


class CapacityMemberUpdate(TeamBoardCommand):
    full_name: str | None = Field(default=None, min_length=1, max_length=220)
    competency: str | None = Field(default=None, min_length=1, max_length=32)
    rate: float | None = Field(default=None, ge=0, le=1)
    vacation_ranges: list[CapacityDateRange] | None = None
    extra_unavailable_ranges: list[CapacityDateRange] | None = None
    ceremony_percent: float | None = Field(default=None, ge=0, le=100)
    risk_percent: float | None = Field(default=None, ge=0, le=100)
    efficiency: float | None = Field(default=None, ge=0, le=1)
    sort_order: int | None = Field(default=None, ge=0)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("ФИО не может быть пустым")
        return value


