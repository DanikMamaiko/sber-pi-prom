import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._base import ORMModel


# Типы событий таймлайна PI-цикла.
EVENT_TYPE_PIR = "pir"
EVENT_TYPE_REGRESSION = "regression"
EVENT_TYPES = [EVENT_TYPE_PIR, EVENT_TYPE_REGRESSION]


class PiEventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    event_date: date
    end_date: date | None = None


class PiEventRead(ORMModel):
    id: uuid.UUID
    name: str
    event_date: date
    end_date: date | None
    event_type: str


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
    end_date: date | None = None


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
    regressions: list[PiCycleSetupEvent] = Field(default_factory=list)
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
    end_date: date | None = None


class PiEventDataUpdate(PiCycleDataCommand):
    name: str = Field(min_length=1, max_length=180)
    date: date
    end_date: date | None = None


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
    end_date: date | None = None


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
    regressions: list[PiEventDataWrite] = Field(default_factory=list)
    teams: list[PiCycleTeamDataWrite] = Field(default_factory=list)
    goal_options: list[PiNamedDataWrite] = Field(default_factory=list)
    tags: list[PiTagDataWrite] = Field(default_factory=list)
    confirm_cascade: bool = False


class PiEventDataRead(BaseModel):
    id: uuid.UUID
    name: str
    date: date
    end_date: date | None
    event_type: str
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
    regressions: list[PiEventDataRead] = Field(default_factory=list)


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
    regressions: list[PiEventDataRead] = Field(default_factory=list)
    teams: list[PiCycleTeamDataRead] = Field(default_factory=list)
    goal_options: list[PiGoalOptionDataRead] = Field(default_factory=list)
    tags: list[PiTagDataRead] = Field(default_factory=list)
    reference_data: PiCycleReferenceDataRead


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
