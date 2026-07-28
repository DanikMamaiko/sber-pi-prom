import uuid

from pydantic import BaseModel, Field


class ProgramBoardEndpoint(BaseModel):
    kind: str = Field(pattern="^(c|w)$")
    ref: str = Field(min_length=1, max_length=80)


class ProgramBoardBend(BaseModel):
    dx: float
    dy: float


class ProgramBoardConnectionWrite(BaseModel):
    id: uuid.UUID | None = None
    client_uid: str = Field(min_length=1, max_length=80)
    source: ProgramBoardEndpoint
    target: ProgramBoardEndpoint
    relation_type: str = Field(default="depends_on", max_length=40)
    bend: ProgramBoardBend | None = None
    sort_order: int = Field(default=0, ge=0)


class ProgramBoardConnectionRead(ProgramBoardConnectionWrite):
    id: uuid.UUID


class ProgramBoardWrite(BaseModel):
    expected_version: int = Field(ge=0)
    connections: list[ProgramBoardConnectionWrite] = Field(default_factory=list)


class ProgramBoardRead(BaseModel):
    initialized: bool
    version: int
    connections: list[ProgramBoardConnectionRead] = Field(default_factory=list)


