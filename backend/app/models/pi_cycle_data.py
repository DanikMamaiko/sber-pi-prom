import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._base import TimestampMixin, TeamType
from app.models.reference import Team


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


