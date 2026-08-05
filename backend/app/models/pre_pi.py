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
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._base import TimestampMixin, InitiativeStatus
from app.models.reference import Team
from app.models.pi_cycle_data import PiCycle
from app.models.backlog import BacklogItem


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
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    attraction_requests: Mapped[list["InitiativeAttraction"]] = relationship(
        back_populates="executor", cascade="all, delete-orphan"
    )


class InitiativeAttraction(Base, TimestampMixin):
    __tablename__ = "initiative_attractions"
    __table_args__ = (
        UniqueConstraint(
            "executor_id",
            "target_initiative_id",
            "target_team_id",
            "sprint_index",
            name="uq_initiative_attraction_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    executor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("initiative_executors.id", ondelete="CASCADE"), nullable=False
    )
    target_initiative_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("initiatives.id", ondelete="CASCADE"), nullable=False
    )
    target_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id"), nullable=False
    )
    sprint_index: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    executor: Mapped[InitiativeExecutor] = relationship(
        back_populates="attraction_requests"
    )
    target_initiative: Mapped[Initiative] = relationship(
        foreign_keys=[target_initiative_id]
    )
    target_team: Mapped[Team] = relationship(foreign_keys=[target_team_id])


