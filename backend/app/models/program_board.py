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


class BoardConnection(Base, TimestampMixin):
    __tablename__ = "board_connections"
    __table_args__ = (
        UniqueConstraint("cycle_id", "client_uid", name="uq_board_connection_client_uid"),
        UniqueConstraint(
            "cycle_id",
            "source_kind",
            "source_id",
            "target_kind",
            "target_id",
            name="uq_board_connection_directed_edge",
        ),
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


