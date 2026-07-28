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
from app.models.pi_cycle_data import PiCycle
from app.models.reference import Tribe, Team
from app.models.pre_pi import Initiative


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
    owner: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    business_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="planned", nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="committed", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    cycle: Mapped[PiCycle] = relationship(back_populates="goals")
    tribe: Mapped[Tribe | None] = relationship()
    team: Mapped[Team | None] = relationship()
    initiative: Mapped[Initiative | None] = relationship()
    initiative_links: Mapped[list["PiGoalInitiative"]] = relationship(
        back_populates="goal",
        cascade="all, delete-orphan",
        order_by="PiGoalInitiative.sort_order",
    )


class PiGoalInitiative(Base):
    __tablename__ = "pi_goal_initiatives"
    __table_args__ = (
        UniqueConstraint("goal_id", "initiative_id", name="uq_pi_goal_initiative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pi_goals.id", ondelete="CASCADE"))
    initiative_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("initiatives.id", ondelete="CASCADE"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    goal: Mapped[PiGoal] = relationship(back_populates="initiative_links")
    initiative: Mapped[Initiative] = relationship()


