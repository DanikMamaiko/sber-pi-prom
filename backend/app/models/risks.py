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
from app.models._base import TimestampMixin, RiskScope
from app.models.pi_cycle_data import PiCycle
from app.models.reference import Tribe, Team
from app.models.pre_pi import Initiative


class Risk(Base, TimestampMixin):
    __tablename__ = "risks"
    __table_args__ = (
        UniqueConstraint("cycle_id", "client_uid", name="uq_cycle_risk_client_uid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pi_cycles.id", ondelete="CASCADE"))
    client_uid: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(40), default=RiskScope.general.value)
    tribe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tribes.id"), nullable=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    initiative_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("initiatives.id"), nullable=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(220), default="")
    impact: Mapped[str] = mapped_column(Text, default="")
    control_point: Mapped[str] = mapped_column(String(220), default="")
    mitigation_plan: Mapped[str] = mapped_column(Text, default="")
    probability: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    impact_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    criticality: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reaction_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    treatment_plan: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    roam: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cycle: Mapped[PiCycle] = relationship(back_populates="risks")
    tribe: Mapped[Tribe | None] = relationship()
    team: Mapped[Team | None] = relationship()
    initiative: Mapped[Initiative | None] = relationship()
