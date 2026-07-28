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
from app.models._base import TimestampMixin
from app.models.reference import Team
from app.models.pi_cycle_data import PiCycle
from app.models.pre_pi import Initiative


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


