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
from app.models.reference import Team, Tribe


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
    tshirt_size: Mapped[str] = mapped_column(String(40), default="", nullable=False)
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


