import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Quarter(str, enum.Enum):
    q1 = "Q1"
    q2 = "Q2"
    q3 = "Q3"
    q4 = "Q4"


class TeamType(str, enum.Enum):
    agile = "Agile"
    it_project = "IT_PROJECT"


class InitiativeStatus(str, enum.Enum):
    backlog = "backlog"
    planned = "planned"
    on_board = "on_board"
    done = "done"


class RiskScope(str, enum.Enum):
    general = "general"
    team = "team"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Tribe(Base, TimestampMixin):
    __tablename__ = "tribes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)

    teams: Mapped[list["Team"]] = relationship(back_populates="tribe", cascade="all, delete-orphan")


class Team(Base, TimestampMixin):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tribe_id", "name", name="uq_team_tribe_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tribe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tribes.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    team_type: Mapped[str] = mapped_column(String(40), default=TeamType.agile.value)
    excluded_from_goals: Mapped[bool] = mapped_column(Boolean, default=False)

    tribe: Mapped[Tribe] = relationship(back_populates="teams")
    competencies: Mapped[list["TeamCompetency"]] = relationship(
        back_populates="team", cascade="all, delete-orphan", order_by="TeamCompetency.sort_order"
    )
    members: Mapped[list["TeamMember"]] = relationship(back_populates="team", cascade="all, delete-orphan")


class TeamCompetency(Base):
    __tablename__ = "team_competencies"
    __table_args__ = (UniqueConstraint("team_id", "code", name="uq_team_competency"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    team: Mapped[Team] = relationship(back_populates="competencies")


class TeamMember(Base, TimestampMixin):
    __tablename__ = "team_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    full_name: Mapped[str] = mapped_column(String(220), nullable=False)
    competency: Mapped[str] = mapped_column(String(32), nullable=False)
    rate: Mapped[float] = mapped_column(Float, default=1.0)
    unavailable_ranges: Mapped[dict] = mapped_column(JSONB, default=dict)
    ceremony_percent: Mapped[float] = mapped_column(Float, default=0)
    risk_percent: Mapped[float] = mapped_column(Float, default=0)
    efficiency_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    team: Mapped[Team] = relationship(back_populates="members")


class PiCycle(Base, TimestampMixin):
    __tablename__ = "pi_cycles"
    __table_args__ = (UniqueConstraint("year", "quarter", name="uq_pi_cycle_year_quarter"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[str] = mapped_column(String(2), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sprint_count: Mapped[int] = mapped_column(Integer, default=6)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    setup_initialized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    initiatives_initialized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    goals_initialized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    boards_initialized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capacity_initialized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    program_board_initialized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risks_initialized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    events: Mapped[list["PiEvent"]] = relationship(back_populates="cycle", cascade="all, delete-orphan")
    cycle_teams: Mapped[list["PiCycleTeam"]] = relationship(
        back_populates="cycle", cascade="all, delete-orphan"
    )
    goal_options: Mapped[list["PiCycleGoalOption"]] = relationship(
        back_populates="cycle", cascade="all, delete-orphan"
    )
    tags: Mapped[list["PiCycleTag"]] = relationship(
        back_populates="cycle", cascade="all, delete-orphan"
    )
    initiatives: Mapped[list["Initiative"]] = relationship(back_populates="cycle", cascade="all, delete-orphan")
    goals: Mapped[list["PiGoal"]] = relationship(back_populates="cycle", cascade="all, delete-orphan")
    risks: Mapped[list["Risk"]] = relationship(back_populates="cycle", cascade="all, delete-orphan")
    connections: Mapped[list["BoardConnection"]] = relationship(back_populates="cycle", cascade="all, delete-orphan")
    capacity_members: Mapped[list["PiCycleCapacityMember"]] = relationship(
        back_populates="cycle", cascade="all, delete-orphan"
    )


class PiEvent(Base):
    __tablename__ = "pi_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pi_cycles.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cycle: Mapped[PiCycle] = relationship(back_populates="events")


class PiCycleTeam(Base):
    __tablename__ = "pi_cycle_teams"
    __table_args__ = (UniqueConstraint("cycle_id", "team_id", name="uq_pi_cycle_team"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pi_cycles.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    team_type: Mapped[str] = mapped_column(String(40), default=TeamType.agile.value)
    excluded_from_goals: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    cycle: Mapped[PiCycle] = relationship(back_populates="cycle_teams")
    team: Mapped[Team] = relationship()
    competencies: Mapped[list["PiCycleTeamCompetency"]] = relationship(
        back_populates="cycle_team",
        cascade="all, delete-orphan",
        order_by="PiCycleTeamCompetency.sort_order",
    )


class PiCycleTeamCompetency(Base):
    __tablename__ = "pi_cycle_team_competencies"
    __table_args__ = (UniqueConstraint("cycle_team_id", "code", name="uq_pi_cycle_team_competency"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pi_cycle_teams.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    cycle_team: Mapped[PiCycleTeam] = relationship(back_populates="competencies")


class PiCycleCapacityMember(Base, TimestampMixin):
    __tablename__ = "pi_cycle_capacity_members"
    __table_args__ = (
        UniqueConstraint("cycle_id", "client_uid", name="uq_cycle_capacity_member_uid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pi_cycles.id", ondelete="CASCADE")
    )
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    client_uid: Mapped[str] = mapped_column(String(80), nullable=False)
    full_name: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    competency: Mapped[str] = mapped_column(String(32), nullable=False)
    rate: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    vacation_ranges: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    extra_unavailable_ranges: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    ceremony_percent: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    risk_percent: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cycle: Mapped[PiCycle] = relationship(back_populates="capacity_members")
    team: Mapped[Team] = relationship()


class PiCycleGoalOption(Base):
    __tablename__ = "pi_cycle_goal_options"
    __table_args__ = (UniqueConstraint("cycle_id", "name", name="uq_pi_cycle_goal_option"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pi_cycles.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(260), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    cycle: Mapped[PiCycle] = relationship(back_populates="goal_options")


class PiCycleTag(Base):
    __tablename__ = "pi_cycle_tags"
    __table_args__ = (UniqueConstraint("cycle_id", "name", name="uq_pi_cycle_tag"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pi_cycles.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    cycle: Mapped[PiCycle] = relationship(back_populates="tags")


class BacklogItem(Base, TimestampMixin):
    __tablename__ = "backlog_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tribe_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tribes.id", ondelete="SET NULL"), nullable=True
    )
    issue_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(260), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    product: Mapped[str] = mapped_column(String(180), default="")
    owner_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    initiative_type: Mapped[str] = mapped_column(String(120), default="")
    target_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_quarter: Mapped[str | None] = mapped_column(String(2), nullable=True)
    customer_priority: Mapped[str] = mapped_column(String(40), default="")
    team_priority: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(80), default="not_estimated")
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    systems: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    sent_to: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    tribe: Mapped[Tribe | None] = relationship()
    owner_team: Mapped[Team | None] = relationship()
    executors: Mapped[list["BacklogExecutor"]] = relationship(
        back_populates="backlog_item",
        cascade="all, delete-orphan",
        order_by="BacklogExecutor.sort_order",
    )


class BacklogBoardState(Base):
    """Singleton marker distinguishing an authoritative empty board from no import yet."""

    __tablename__ = "backlog_board_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    initialized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class BacklogExecutor(Base):
    __tablename__ = "backlog_executors"
    __table_args__ = (UniqueConstraint("backlog_item_id", "team_id", name="uq_backlog_executor_team"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    backlog_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backlog_items.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"))
    effort_by_competency: Mapped[dict] = mapped_column(JSONB, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    backlog_item: Mapped[BacklogItem] = relationship(back_populates="executors")
    team: Mapped[Team] = relationship()


class Initiative(Base, TimestampMixin):
    __tablename__ = "initiatives"
    __table_args__ = (UniqueConstraint("cycle_id", "issue_key", name="uq_cycle_initiative_issue"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pi_cycles.id", ondelete="CASCADE"))
    backlog_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("backlog_items.id"), nullable=True)
    issue_key: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(260), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    product: Mapped[str] = mapped_column(String(180), default="")
    owner_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    initiative_type: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default=InitiativeStatus.backlog.value)
    goal_text: Mapped[str] = mapped_column(String(260), default="")
    metric: Mapped[str] = mapped_column(String(260), default="")
    current_value: Mapped[str] = mapped_column(String(260), default="")
    target_value: Mapped[str] = mapped_column(String(260), default="")
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    redesign: Mapped[str] = mapped_column(Text, default="")
    customer_priority: Mapped[str] = mapped_column(String(40), default="")
    team_priority: Mapped[str] = mapped_column(String(40), default="")
    estimate: Mapped[str] = mapped_column(String(120), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    pre_planned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    on_board: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    agreed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    sprint_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    week_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    board_sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cycle: Mapped[PiCycle] = relationship(back_populates="initiatives")
    backlog_item: Mapped[BacklogItem | None] = relationship()
    owner_team: Mapped[Team | None] = relationship()
    executors: Mapped[list["InitiativeExecutor"]] = relationship(
        back_populates="initiative", cascade="all, delete-orphan"
    )
    stories: Mapped[list["Story"]] = relationship(back_populates="initiative", cascade="all, delete-orphan")
    work_items: Mapped[list["WorkItem"]] = relationship(back_populates="initiative", cascade="all, delete-orphan")


class InitiativeExecutor(Base):
    __tablename__ = "initiative_executors"
    __table_args__ = (UniqueConstraint("initiative_id", "team_id", name="uq_initiative_executor_team"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    initiative_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("initiatives.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"))
    effort_by_competency: Mapped[dict] = mapped_column(JSONB, default=dict)
    attractions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    initiative: Mapped[Initiative] = relationship(back_populates="executors")
    team: Mapped[Team] = relationship()


class Story(Base, TimestampMixin):
    __tablename__ = "stories"
    __table_args__ = (UniqueConstraint("initiative_id", "client_uid", name="uq_story_client_uid"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    initiative_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("initiatives.id", ondelete="CASCADE"))
    client_uid: Mapped[str] = mapped_column(String(80), nullable=False)
    external_key: Mapped[str] = mapped_column(String(80), default="")
    title: Mapped[str] = mapped_column(String(260), nullable=False)
    effort_by_competency: Mapped[dict] = mapped_column(JSONB, default=dict)
    sprint_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    week_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    board_sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    initiative: Mapped[Initiative] = relationship(back_populates="stories")
    work_items: Mapped[list["WorkItem"]] = relationship(back_populates="story", cascade="all, delete-orphan")


class WorkItem(Base, TimestampMixin):
    __tablename__ = "work_items"
    __table_args__ = (UniqueConstraint("initiative_id", "client_uid", name="uq_work_item_client_uid"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    initiative_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("initiatives.id", ondelete="CASCADE"))
    story_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), nullable=True)
    client_uid: Mapped[str] = mapped_column(String(80), nullable=False)
    assignee_name: Mapped[str] = mapped_column(String(220), default="")
    competency: Mapped[str] = mapped_column(String(32), nullable=False)
    effort: Mapped[float] = mapped_column(Float, default=0)
    sprint_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    week_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    board_sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    initiative: Mapped[Initiative] = relationship(back_populates="work_items")
    story: Mapped[Story | None] = relationship(back_populates="work_items")


class PiGoal(Base, TimestampMixin):
    __tablename__ = "pi_goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pi_cycles.id", ondelete="CASCADE"))
    tribe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tribes.id"), nullable=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    initiative_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("initiatives.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(260), nullable=False)
    metric: Mapped[str] = mapped_column(String(260), default="")
    current_value: Mapped[str] = mapped_column(String(260), default="")
    target_value: Mapped[str] = mapped_column(String(260), default="")
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    redesign: Mapped[str] = mapped_column(Text, default="")
    product: Mapped[str] = mapped_column(String(180), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    cycle: Mapped[PiCycle] = relationship(back_populates="goals")
    tribe: Mapped[Tribe | None] = relationship()
    team: Mapped[Team | None] = relationship()
    initiative: Mapped[Initiative | None] = relationship()


class BoardConnection(Base, TimestampMixin):
    __tablename__ = "board_connections"
    __table_args__ = (
        UniqueConstraint("cycle_id", "client_uid", name="uq_board_connection_client_uid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pi_cycles.id", ondelete="CASCADE"))
    client_uid: Mapped[str] = mapped_column(String(80), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(40), default="depends_on")
    bend_dx: Mapped[float | None] = mapped_column(Float, nullable=True)
    bend_dy: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cycle: Mapped[PiCycle] = relationship(back_populates="connections")


class Risk(Base, TimestampMixin):
    __tablename__ = "risks"
    __table_args__ = (
        UniqueConstraint("cycle_id", "client_uid", name="uq_cycle_risk_client_uid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pi_cycles.id", ondelete="CASCADE"))
    client_uid: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(40), default=RiskScope.general.value)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(220), default="")
    impact: Mapped[str] = mapped_column(Text, default="")
    control_point: Mapped[str] = mapped_column(String(220), default="")
    mitigation_plan: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cycle: Mapped[PiCycle] = relationship(back_populates="risks")
    team: Mapped[Team | None] = relationship()
