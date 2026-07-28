import enum
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

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


