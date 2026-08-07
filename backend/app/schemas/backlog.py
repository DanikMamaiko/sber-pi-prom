import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# «Размер майки» (T-shirt sizing). Пустая строка = значение не выбрано.
TShirtSize = Literal["", "XS", "S", "M", "L", "XL", "Megalodon"]
TSHIRT_SIZES: tuple[str, ...] = ("", "XS", "S", "M", "L", "XL", "Megalodon")


class BacklogExecutorPayload(BaseModel):
    team_id: uuid.UUID
    effort_by_competency: dict[str, float] = Field(default_factory=dict)


class BacklogBoardExecutor(BaseModel):
    id: uuid.UUID | None = None
    team: str = Field(default="", max_length=180)
    effort_by_competency: dict[str, float] = Field(default_factory=dict)


class BacklogBoardExecutorRead(BacklogBoardExecutor):
    id: uuid.UUID


# Editable fields shared by the single-item command DTO and the bulk form DTO.
# Server-managed attributes (id, sort_order, sent_to, total_effort) live only on
# the read model or on the dedicated command that owns them.
# Editable fields shared by the single-item command DTO and the bulk form DTO.
# Server-managed attributes (id, sort_order, sent_to, total_effort) live only on
# the read model or on the dedicated command that owns them.
class BacklogItemFields(BaseModel):
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
    tshirt_size: TShirtSize = ""
    tags: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    executors: list[BacklogBoardExecutor] = Field(default_factory=list)


class BacklogItemCommand(BacklogItemFields):
    """One user action (create or edit one initiative) = one backend command."""

    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)


class BacklogItemDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    confirm_cascade: bool = False


class BacklogReorderCommand(BaseModel):
    """Full canonical order of every backlog item after a drag."""

    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    item_ids: list[uuid.UUID] = Field(min_length=1)


class BacklogBoardItemWrite(BacklogItemFields):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID | None = None
    sort_order: int = Field(default=0, ge=0)


class BacklogBoardWrite(BaseModel):
    """Bulk 'save form' command: replaces the whole board in one transaction."""

    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    items: list[BacklogBoardItemWrite] = Field(default_factory=list)
    confirm_cascade: bool = False


class BacklogTribeRef(BaseModel):
    id: uuid.UUID
    name: str


class BacklogTeamRef(BaseModel):
    id: uuid.UUID
    tribe_id: uuid.UUID
    tribe: str
    name: str
    competencies: list[str] = Field(default_factory=list)


class BacklogReferenceDataRead(BaseModel):
    tribes: list[BacklogTribeRef] = Field(default_factory=list)
    teams: list[BacklogTeamRef] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    competencies: list[str] = Field(default_factory=list)


class BacklogBoardItemRead(BacklogItemFields):
    id: uuid.UUID
    sort_order: int
    sent_to: list[str] = Field(default_factory=list)
    total_effort: float = 0.0
    executors: list[BacklogBoardExecutorRead] = Field(default_factory=list)


class BacklogBoardRead(BaseModel):
    cycle_id: uuid.UUID | None = None
    initialized: bool
    version: int
    items: list[BacklogBoardItemRead] = Field(default_factory=list)
    reference_data: BacklogReferenceDataRead


class BacklogDispatchWrite(BaseModel):
    """Atomic transfer of a tribe's matching initiatives into a PI-cycle.

    The target cycle is resolved server-side from target_year/target_quarter,
    so the frontend never decides which initiatives are eligible.
    """

    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    tribe: str = Field(min_length=1, max_length=180)
    target_year: int = Field(ge=2026, le=2100)
    target_quarter: str = Field(pattern="^Q[1-4]$")


