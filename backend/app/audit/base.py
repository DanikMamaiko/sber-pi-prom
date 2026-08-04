from sqlalchemy.orm import DeclarativeBase


class AuditBase(DeclarativeBase):
    """Metadata isolated from the business database metadata."""
