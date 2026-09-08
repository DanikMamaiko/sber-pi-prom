from pydantic import BaseModel, ConfigDict, Field

from app.schemas.backlog import BacklogBoardRead


class JiraIssueRead(BaseModel):
    issue_key: str
    title: str = ""
    user_products: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    infrastructures: list[str] = Field(default_factory=list)
    owner_teams: list[str] = Field(default_factory=list)
    executor_teams: list[str] = Field(default_factory=list)
    initiative_type: str = ""
    original_estimate_days: float | None = None
    refined_estimate_days: float | None = None
    effort_by_work_type: dict[str, float] = Field(default_factory=dict)
    effort_by_competency: dict[str, float] = Field(default_factory=dict)
    synced_at: str


class JiraBacklogImportCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_key: str = Field(min_length=1, max_length=80)
    tribe: str = Field(min_length=1, max_length=180)
    fallback_team: str = Field(default="", max_length=180)
    expected_version: int = Field(ge=0)


class JiraBacklogImportRead(BaseModel):
    board: BacklogBoardRead
    jira: JiraIssueRead
    warnings: list[str] = Field(default_factory=list)
