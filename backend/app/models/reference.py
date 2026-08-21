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


