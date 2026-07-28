import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PiEventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    event_date: date


class PiEventRead(ORMModel):
    id: uuid.UUID
    name: str
    event_date: date


class PiCycleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=2026, le=2100)
    quarter: str = Field(pattern="^Q[1-4]$")
    start_date: date | None = None
    sprint_count: int = Field(default=6, ge=1, le=20)


class PiCycleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date | None = None
    sprint_count: int | None = Field(default=None, ge=1, le=20)
    status: str | None = None
    expected_version: int = Field(ge=0)


class PiCycleRead(ORMModel):
    id: uuid.UUID
    year: int
    quarter: str
    start_date: date | None
    sprint_count: int
    status: str
    version: int
    setup_initialized: bool
    initiatives_initialized: bool
    goals_initialized: bool
    boards_initialized: bool
    capacity_initialized: bool
    program_board_initialized: bool
    risks_initialized: bool


class PiCycleSetupEvent(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    date: date


class PiCycleSetupTeam(BaseModel):
    tribe: str = Field(min_length=1, max_length=180)
    name: str = Field(min_length=1, max_length=180)
    team_type: str = Field(default="Agile", pattern="^(Agile|ИТ-проект)$")
    excluded_from_goals: bool = False
    competencies: list[str] = Field(default_factory=list)


class PiCycleSetupData(BaseModel):
    start_date: date | None = None
    sprint_count: int = Field(default=6, ge=1, le=20)
    pirs: list[PiCycleSetupEvent] = Field(default_factory=list)
    teams: list[PiCycleSetupTeam] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PiCycleSetupWrite(PiCycleSetupData):
    expected_version: int = Field(ge=0)


class PiCycleSetupRead(PiCycleSetupData):
    initialized: bool
    version: int


class PiCycleDataCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)


class PiCycleDataUpdate(PiCycleDataCommand):
    start_date: date | None = None
    sprint_count: int = Field(ge=1, le=20)
    cascade_policy: str | None = Field(
        default=None,
        pattern="^(unassign_out_of_range)$",
    )


class PiEventDataCreate(PiCycleDataCommand):
    name: str = Field(min_length=1, max_length=180)
    date: date


class PiEventDataUpdate(PiCycleDataCommand):
    name: str = Field(min_length=1, max_length=180)
    date: date


class PiCycleTeamDataCreate(PiCycleDataCommand):
    tribe: str = Field(min_length=1, max_length=180)
    name: str = Field(min_length=1, max_length=180)
    team_type: str = Field(default="Agile", pattern="^(Agile|ИТ-проект)$")
    excluded_from_goals: bool = False
    competencies: list[str] = Field(min_length=1)


class PiCycleTeamDataUpdate(PiCycleTeamDataCreate):
    cascade_policy: str | None = Field(
        default=None,
        pattern="^(remove_competency_usage)$",
    )


class PiCycleTeamDelete(PiCycleDataCommand):
    confirm_cascade: bool = False


class PiGoalOptionDataCreate(PiCycleDataCommand):
    name: str = Field(min_length=1, max_length=260)


class PiGoalOptionDataUpdate(PiCycleDataCommand):
    name: str = Field(min_length=1, max_length=260)


class PiTagDataCreate(PiCycleDataCommand):
    name: str = Field(min_length=1, max_length=120)


class PiTagDataUpdate(PiCycleDataCommand):
    name: str = Field(min_length=1, max_length=120)


class PiEventDataWrite(BaseModel):
    id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=180)
    date: date


class PiCycleTeamDataWrite(BaseModel):
    id: uuid.UUID | None = None
    tribe: str = Field(min_length=1, max_length=180)
    name: str = Field(min_length=1, max_length=180)
    team_type: str = Field(default="Agile", pattern="^(Agile|ИТ-проект)$")
    excluded_from_goals: bool = False
    competencies: list[str] = Field(min_length=1)


class PiNamedDataWrite(BaseModel):
    id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=260)


class PiTagDataWrite(BaseModel):
    id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=120)


class PiCycleDataReplace(PiCycleDataCommand):
    start_date: date | None = None
    sprint_count: int = Field(ge=1, le=20)
    pirs: list[PiEventDataWrite] = Field(default_factory=list)
    teams: list[PiCycleTeamDataWrite] = Field(default_factory=list)
    goal_options: list[PiNamedDataWrite] = Field(default_factory=list)
    tags: list[PiTagDataWrite] = Field(default_factory=list)
    confirm_cascade: bool = False


class PiEventDataRead(BaseModel):
    id: uuid.UUID
    name: str
    date: date
    sort_order: int


class PiCycleTeamDataRead(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    tribe_id: uuid.UUID
    tribe: str
    name: str
    team_type: str
    excluded_from_goals: bool
    competencies: list[str] = Field(default_factory=list)
    sort_order: int


class PiGoalOptionDataRead(BaseModel):
    id: uuid.UUID
    name: str
    sort_order: int


class PiTagDataRead(BaseModel):
    id: uuid.UUID
    name: str
    sort_order: int


class PiScheduleWeekRead(BaseModel):
    index: int
    start_date: date
    end_date: date
    workdays: int


class PiScheduleSprintRead(BaseModel):
    index: int
    title: str
    start_date: date
    end_date: date
    workdays: int
    weeks: list[PiScheduleWeekRead] = Field(default_factory=list)
    pirs: list[PiEventDataRead] = Field(default_factory=list)


class PiScheduleRead(BaseModel):
    end_date: date | None
    total_workdays: int
    sprints: list[PiScheduleSprintRead] = Field(default_factory=list)


class PiCycleReferenceDataRead(BaseModel):
    team_types: list[str]
    competencies: list[str]
    sprint_count_min: int
    sprint_count_max: int


class PiCycleDataRead(BaseModel):
    cycle: PiCycleRead
    schedule: PiScheduleRead
    pirs: list[PiEventDataRead] = Field(default_factory=list)
    teams: list[PiCycleTeamDataRead] = Field(default_factory=list)
    goal_options: list[PiGoalOptionDataRead] = Field(default_factory=list)
    tags: list[PiTagDataRead] = Field(default_factory=list)
    reference_data: PiCycleReferenceDataRead


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


class BacklogExecutorPayload(BaseModel):
    team_id: uuid.UUID
    effort_by_competency: dict[str, float] = Field(default_factory=dict)


class BacklogItemCreate(BaseModel):
    issue_key: str
    title: str
    description: str = ""
    product: str = ""
    owner_team_id: uuid.UUID | None = None
    initiative_type: str = ""
    target_year: int | None = None
    target_quarter: str | None = None
    customer_priority: str = ""
    team_priority: str = ""
    tags: list[str] = Field(default_factory=list)
    executors: list[BacklogExecutorPayload] = Field(default_factory=list)


class BacklogItemRead(ORMModel):
    id: uuid.UUID
    issue_key: str
    title: str
    description: str
    product: str
    owner_team_id: uuid.UUID | None
    initiative_type: str
    target_year: int | None
    target_quarter: str | None
    customer_priority: str
    team_priority: str
    status: str
    tags: list[str]


class BacklogBoardExecutor(BaseModel):
    team: str = Field(default="", max_length=180)
    effort_by_competency: dict[str, float] = Field(default_factory=dict)


class BacklogBoardItemWrite(BaseModel):
    id: uuid.UUID | None = None
    tribe: str = Field(min_length=1, max_length=180)
    issue_key: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=260)
    description: str = ""
    product: str = Field(default="", max_length=180)
    owner_team: str = Field(default="", max_length=180)
    initiative_type: str = Field(default="", max_length=120)
    target_year: int | None = Field(default=None, ge=2020, le=2100)
    target_quarter: str | None = Field(default=None, pattern="^Q[1-4]$")
    customer_priority: str = Field(default="", max_length=40)
    team_priority: str = Field(default="", max_length=40)
    status: str = Field(default="Нет оценки", max_length=80)
    systems: list[str] = Field(default_factory=list)
    sent_to: list[str] = Field(default_factory=list)
    sort_order: int = Field(default=0, ge=0)
    executors: list[BacklogBoardExecutor] = Field(default_factory=list)


class BacklogBoardItemRead(BacklogBoardItemWrite):
    id: uuid.UUID


class BacklogBoardWrite(BaseModel):
    expected_version: int = Field(ge=0)
    items: list[BacklogBoardItemWrite] = Field(default_factory=list)


class BacklogBoardRead(BaseModel):
    initialized: bool
    version: int
    items: list[BacklogBoardItemRead] = Field(default_factory=list)


class BacklogDispatchWrite(BaseModel):
    expected_version: int = Field(ge=0)
    backlog_item_ids: list[uuid.UUID] = Field(min_length=1)


class BacklogDispatchRead(BaseModel):
    cycle_id: uuid.UUID
    version: int
    dispatched: int
    initiatives: list["InitiativeRead"]


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


BacklogDispatchRead.model_rebuild()


class PrePiAttraction(BaseModel):
    issue_key: str = Field(min_length=1, max_length=80)
    team: str = Field(default="", max_length=180)
    sprint_index: int | None = Field(default=None, ge=0)


class PrePiExecutor(BaseModel):
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


class PrePiWrite(BaseModel):
    expected_version: int = Field(ge=0)
    initiatives: list[PrePiInitiativeWrite] = Field(default_factory=list)


class PrePiRead(BaseModel):
    initialized: bool
    version: int
    initiatives: list[PrePiInitiativeRead] = Field(default_factory=list)


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


class CapacityDateRange(BaseModel):
    start: date
    end: date


class CapacityMemberWrite(BaseModel):
    id: uuid.UUID | None = None
    client_uid: str = Field(min_length=1, max_length=80)
    full_name: str = Field(default="", max_length=220)
    competency: str = Field(min_length=1, max_length=32)
    rate: float = Field(default=1, ge=0, le=1)
    vacation_ranges: list[CapacityDateRange] = Field(default_factory=list)
    extra_unavailable_ranges: list[CapacityDateRange] = Field(default_factory=list)
    ceremony_percent: float = Field(default=0, ge=0, le=100)
    risk_percent: float = Field(default=0, ge=0, le=100)
    efficiency: float | None = Field(default=None, ge=0, le=1)
    sort_order: int = Field(default=0, ge=0)


class CapacitySprintRead(BaseModel):
    sprint_index: int
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


class CapacityWrite(BaseModel):
    expected_version: int = Field(ge=0)
    teams: list[CapacityTeamWrite] = Field(default_factory=list)


class CapacityRead(BaseModel):
    initialized: bool
    version: int
    teams: list[CapacityTeamRead] = Field(default_factory=list)


class ProgramBoardEndpoint(BaseModel):
    kind: str = Field(pattern="^(c|w)$")
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
    connections: list[ProgramBoardConnectionRead] = Field(default_factory=list)


class GoalsItemWrite(BaseModel):
    id: uuid.UUID | None = None
    tribe: str = Field(min_length=1, max_length=180)
    team: str = Field(min_length=1, max_length=180)
    issue_key: str = Field(min_length=1, max_length=80)
    initiative_title: str = Field(default="", max_length=260)
    goal_text: str = Field(default="", max_length=260)
    product: str = Field(default="", max_length=180)
    metric: str = Field(default="", max_length=260)
    current_value: str = Field(default="", max_length=260)
    target_value: str = Field(default="", max_length=260)
    hypothesis: str = ""
    redesign: str = ""
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
    scope: str = Field(pattern="^(general|team)$")
    team: RiskTeamRef | None = None
    is_shared: bool = False
    description: str = Field(min_length=1)
    owner: str = Field(default="", max_length=220)
    impact: str = ""
    control_point: str = Field(default="", max_length=220)
    mitigation_plan: str = ""
    sort_order: int = Field(default=0, ge=0)


class RiskItemRead(RiskItemWrite):
    id: uuid.UUID


class RisksWrite(BaseModel):
    expected_version: int = Field(ge=0)
    risks: list[RiskItemWrite] = Field(default_factory=list)


class RisksRead(BaseModel):
    initialized: bool
    version: int
    risks: list[RiskItemRead] = Field(default_factory=list)


class SprintRead(BaseModel):
    index: int
    title: str
    start_date: date
    end_date: date

class OverviewRead(BaseModel):
    cycle: PiCycleRead
    sprints: list[SprintRead]
    teams_count: int
    backlog_count: int
    initiatives_count: int
    goals_count: int
    risks_count: int
